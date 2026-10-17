"""大模型后端：给定系统提示词、工具子集与首条消息，运行工具调用循环直到角色交回。

run() 的 dispatch(name, args) 返回 (结果, 是否结束本角色)。Claude 与 Ollama 共用同一接口，
单智能体与多智能体两种模式都经由这里调用基座模型（论文 H2 的跨基座比较）。
"""
import http.client
import json
import urllib.error
import urllib.request

from .tools import tool_defs

MAX_NUDGES = 2
NUDGE = ('You have not finished your task. Continue by calling tools; when your task is complete call handoff '
         '(or finish, if that is your final step).')


def _dump(obj):
    return json.dumps(obj, ensure_ascii=False, default=str)


class ClaudeBackend:
    FALLBACK_MODELS = {'claude-opus-5', 'claude-fable-5', 'claude-fable-5-1'}   # 支持服务端 fallbacks 的模型

    def __init__(self, model='claude-opus-5', effort='high', client=None):
        import anthropic
        self.model = model
        self.effort = effort
        self.client = client or anthropic.Anthropic()

    def _call(self, system, tools, messages):
        kw = dict(model=self.model, max_tokens=16000, tools=tools, messages=messages,
                  system=[{'type': 'text', 'text': system}], output_config={'effort': self.effort})
        if self.model in self.FALLBACK_MODELS:
            return self.client.beta.messages.create(betas=['server-side-fallback-2026-07-01'],
                                                    fallbacks='default', **kw)
        return self.client.messages.create(**kw)

    def run(self, system, tool_names, user_text, dispatch, is_done=lambda: False, max_turns=80):
        tools = [dict(t) for t in tool_defs(tool_names)]
        tools[-1]['cache_control'] = {'type': 'ephemeral'}     # 工具与系统提示词为稳定前缀
        messages = [{'role': 'user', 'content': user_text}]
        usage = {'turns': 0, 'input_tokens': 0, 'output_tokens': 0, 'cache_read_input_tokens': 0,
                 'cache_creation_input_tokens': 0, 'ended': 'max_turns'}
        nudges = 0
        for _ in range(max_turns):
            resp = self._call(system, tools, messages)
            usage['turns'] += 1
            for k in ('input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens'):
                usage[k] += getattr(resp.usage, k, 0) or 0
            if resp.stop_reason == 'refusal':
                usage['ended'] = 'refusal'
                break
            messages.append({'role': 'assistant', 'content': resp.content})
            if resp.stop_reason == 'max_tokens':
                messages.append({'role': 'user', 'content': 'Your last turn hit the output limit. Continue with '
                                 'smaller steps.'})
                continue
            calls = [b for b in resp.content if b.type == 'tool_use']
            if not calls:
                if is_done() or nudges >= MAX_NUDGES:
                    usage['ended'] = 'no_tool_call'
                    break
                nudges += 1
                messages.append({'role': 'user', 'content': NUDGE})
                continue
            results, stop = [], False
            for b in calls:
                out, s = dispatch(b.name, b.input if isinstance(b.input, dict) else {})
                stop = stop or s
                results.append({'type': 'tool_result', 'tool_use_id': b.id, 'content': _dump(out),
                                'is_error': isinstance(out, dict) and 'error' in out})
            messages.append({'role': 'user', 'content': results})
            if stop or is_done():
                usage['ended'] = 'handoff'
                break
        return usage


class OllamaBackend:
    """本地开源模型（Ollama /api/chat）。小模型上下文有限，较早的工具结果截短。"""
    KEEP_FULL = 24
    TRUNCATE_TO = 300

    def __init__(self, model='qwen3.5:9b', host='http://localhost:11434', num_ctx=32768, think=True, timeout=900):
        self.model = model
        self.url = host.rstrip('/') + '/api/chat'
        self.options = {'num_ctx': num_ctx}
        self.think = think
        self.timeout = timeout

    def _chat(self, messages, tools):
        body = json.dumps({'model': self.model, 'messages': messages, 'tools': tools, 'stream': False,
                           'think': self.think, 'options': self.options}).encode()
        req = urllib.request.Request(self.url, data=body, headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read())
        except urllib.error.URLError as e:
            raise RuntimeError(f'无法连接 Ollama（{self.url}）：{e}。请先运行 `ollama serve` 并 '
                               f'`ollama pull {self.model}`') from e

    def run(self, system, tool_names, user_text, dispatch, is_done=lambda: False, max_turns=80):
        tools = [{'type': 'function', 'function': {'name': t['name'], 'description': t['description'],
                                                   'parameters': t['input_schema']}} for t in tool_defs(tool_names)]
        messages = [{'role': 'system', 'content': system}, {'role': 'user', 'content': user_text}]
        usage = {'turns': 0, 'prompt_tokens': 0, 'output_tokens': 0, 'ended': 'max_turns'}
        nudges = 0
        for _ in range(max_turns):
            for m in messages[2:-self.KEEP_FULL]:
                if m['role'] == 'tool' and len(m['content']) > self.TRUNCATE_TO:
                    m['content'] = m['content'][:self.TRUNCATE_TO] + ' …(truncated)'
            resp = self._chat(messages, tools)
            usage['turns'] += 1
            usage['prompt_tokens'] += resp.get('prompt_eval_count', 0)
            usage['output_tokens'] += resp.get('eval_count', 0)
            msg = resp['message']
            calls = msg.get('tool_calls') or []
            messages.append({'role': 'assistant', 'content': msg.get('content', ''),
                             **({'tool_calls': calls} if calls else {})})
            if not calls:
                if is_done() or nudges >= MAX_NUDGES:
                    usage['ended'] = 'no_tool_call'
                    break
                nudges += 1
                messages.append({'role': 'user', 'content': NUDGE})
                continue
            stop = False
            for c in calls:
                fn = c.get('function', {})
                args = fn.get('arguments') or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {'__invalid__': args}
                out, s = dispatch(fn.get('name'), args)
                stop = stop or s
                messages.append({'role': 'tool', 'tool_name': fn.get('name'), 'content': _dump(out)})
            if stop or is_done():
                usage['ended'] = 'handoff'
                break
        return usage


def session_dispatch(session, allowed, stop_tools=('finish',)):
    """把工具调用路由到会话方法；只允许 allowed 中的工具。"""
    def dispatch(name, args):
        if name not in allowed or not hasattr(session, name):
            return {'error': f'tool {name} is not available to this agent'}, False
        if '__invalid__' in args:
            return {'error': f'arguments for {name} are not valid JSON'}, False
        try:
            out = getattr(session, name)(**args)
        except TypeError as e:
            return {'error': f'invalid arguments for {name}: {e}'}, False
        return out, name in stop_tools and isinstance(out, dict) and out.get('ok')
    return dispatch


class DeepSeekBackend:
    """DeepSeek API（OpenAI 兼容的 /chat/completions）。

    API 密钥从环境变量读取（默认 DEEPSEEK_API_KEY），不写入代码或命令行。
    思考模式下带工具调用时，assistant 消息的 reasoning_content 必须原样传回，否则接口返回 400。
    """

    def __init__(self, model='deepseek-flash', base_url='https://api.deepseek.com', api_key_env='DEEPSEEK_API_KEY',
                 think=False, timeout=600, max_retries=3):
        import os
        self.key = os.environ.get(api_key_env)
        if not self.key:
            raise RuntimeError(f'未找到环境变量 {api_key_env}。请先在终端执行 export {api_key_env}=你的密钥 '
                               f'（或写入 ~/.zshrc），再运行。')
        self.model = model
        self.url = base_url.rstrip('/') + '/chat/completions'
        self.think = think
        self.timeout = timeout
        self.max_retries = max_retries

    def _chat(self, messages, tools, max_tokens=None):
        import time
        req_body = {'model': self.model, 'messages': messages,
                    'thinking': {'type': 'enabled' if self.think else 'disabled'}}
        if tools:
            req_body['tools'] = tools
        if max_tokens:
            req_body['max_tokens'] = max_tokens
        body = json.dumps(req_body).encode()
        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(self.url, data=body, headers={
                'Content-Type': 'application/json', 'Authorization': f'Bearer {self.key}'})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors='replace')[:500]
                if e.code in (429, 500, 502, 503) and attempt < self.max_retries:
                    time.sleep(2 ** attempt * 5)
                    continue
                raise RuntimeError(f'DeepSeek API 错误 {e.code}：{detail}') from e
            except (urllib.error.URLError, http.client.HTTPException, ConnectionError, TimeoutError) as e:
                if attempt < self.max_retries:           # 连接中断、超时等网络异常：退避后重试
                    time.sleep(2 ** attempt * 5)
                    continue
                raise RuntimeError(f'无法连接 DeepSeek API：{e}') from e

    def complete(self, system, user_text, max_tokens=65536):
        """单次调用、不带工具（直接生成基线 C0/C1）。返回 (回答文本, 用量)。"""
        resp = self._chat([{'role': 'system', 'content': system}, {'role': 'user', 'content': user_text}], None,
                          max_tokens=max_tokens)
        u = resp.get('usage') or {}
        msg = resp['choices'][0]['message']
        usage = {'turns': 1, 'prompt_tokens': u.get('prompt_tokens', 0), 'output_tokens': u.get('completion_tokens', 0),
                 'cache_hit_tokens': u.get('prompt_cache_hit_tokens', 0),
                 'reasoning_chars': len(msg.get('reasoning_content') or ''),
                 'finish_reason': resp['choices'][0].get('finish_reason')}
        return msg.get('content') or '', usage

    def run(self, system, tool_names, user_text, dispatch, is_done=lambda: False, max_turns=80):
        tools = [{'type': 'function', 'function': {'name': t['name'], 'description': t['description'],
                                                   'parameters': t['input_schema']}} for t in tool_defs(tool_names)]
        messages = [{'role': 'system', 'content': system}, {'role': 'user', 'content': user_text}]
        usage = {'turns': 0, 'prompt_tokens': 0, 'output_tokens': 0, 'cache_hit_tokens': 0, 'ended': 'max_turns'}
        nudges = 0
        for _ in range(max_turns):
            resp = self._chat(messages, tools)
            usage['turns'] += 1
            u = resp.get('usage') or {}
            usage['prompt_tokens'] += u.get('prompt_tokens', 0)
            usage['output_tokens'] += u.get('completion_tokens', 0)
            usage['cache_hit_tokens'] += u.get('prompt_cache_hit_tokens', 0)
            msg = resp['choices'][0]['message']
            calls = msg.get('tool_calls') or []
            keep = {'role': 'assistant', 'content': msg.get('content') or ''}
            if msg.get('reasoning_content') is not None:
                keep['reasoning_content'] = msg['reasoning_content']      # 思考模式下必须原样传回
            if calls:
                keep['tool_calls'] = calls
            messages.append(keep)
            if not calls:
                if is_done() or nudges >= MAX_NUDGES:
                    usage['ended'] = 'no_tool_call'
                    break
                nudges += 1
                messages.append({'role': 'user', 'content': NUDGE})
                continue
            stop = False
            for c in calls:
                fn = c.get('function', {})
                try:
                    args = json.loads(fn.get('arguments') or '{}')
                except json.JSONDecodeError:
                    args = {'__invalid__': fn.get('arguments')}
                out, s = dispatch(fn.get('name'), args if isinstance(args, dict) else {'__invalid__': args})
                stop = stop or s
                messages.append({'role': 'tool', 'tool_call_id': c.get('id'), 'content': _dump(out)})
            if stop or is_done():
                usage['ended'] = 'handoff'
                break
        return usage


class OpenAIBackend(DeepSeekBackend):
    """OpenAI 兼容接口（GPT 官方 API 或第三方中转）。

    密钥与地址从环境变量读取：OPENAI_API_KEY、OPENAI_BASE_URL（须含 /v1，如 https://api.openai.com/v1）。
    与 DeepSeek 的区别：不发送 thinking 参数；缓存命中 token 取自 usage.prompt_tokens_details.cached_tokens。
    """

    MAX_OUTPUT = 128000        # GPT 系列单次输出上限（含推理 token）

    def __init__(self, model='gpt-4.1', base_url=None, api_key_env='OPENAI_API_KEY', timeout=600, max_retries=25,
                 reasoning_effort=None):
        import os
        self.key = os.environ.get(api_key_env)
        if not self.key:
            raise RuntimeError(f'未找到环境变量 {api_key_env}。请在 ~/.zshrc 中写入 export {api_key_env}=你的密钥 后重开终端。')
        base = base_url or os.environ.get('OPENAI_BASE_URL') or 'https://api.openai.com/v1'
        self.model = model
        self.url = base.rstrip('/') + '/chat/completions'
        self.think = False
        self.reasoning_effort = reasoning_effort
        self.timeout = timeout
        self.max_retries = max_retries

    def _chat(self, messages, tools, max_tokens=None):
        import time
        body = {'model': self.model, 'messages': messages}
        if tools:
            body['tools'] = tools
        if max_tokens:
            body['max_completion_tokens'] = min(max_tokens, self.MAX_OUTPUT)
        if self.reasoning_effort:
            body['reasoning_effort'] = self.reasoning_effort
        data = json.dumps(body).encode()
        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(self.url, data=data, headers={
                'Content-Type': 'application/json', 'Authorization': f'Bearer {self.key}'})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    resp = json.loads(r.read())
                u = resp.get('usage') or {}
                if 'prompt_cache_hit_tokens' not in u:
                    u['prompt_cache_hit_tokens'] = (u.get('prompt_tokens_details') or {}).get('cached_tokens', 0)
                    resp['usage'] = u
                return resp
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors='replace')[:500]
                if e.code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                    time.sleep(min(2 ** attempt * 5, 60))   # 中转站短时不可用：最长约 20 分钟
                    continue
                raise RuntimeError(f'OpenAI 接口错误 {e.code}：{detail}') from e
            except (urllib.error.URLError, http.client.HTTPException, ConnectionError, TimeoutError) as e:
                if attempt < self.max_retries:           # 连接中断、超时等网络异常：退避后重试
                    time.sleep(min(2 ** attempt * 5, 60))   # 中转站短时不可用：最长约 20 分钟
                    continue
                raise RuntimeError(f'无法连接 OpenAI 接口（{self.url}）：{e}') from e


def _openai_complete_stream(self, system, user_text, max_tokens=65536):
    """单次长调用改用流式返回：推理模型长时间思考时连接保持活动，中转网关不会因空闲而断开。"""
    import time
    body = {'model': self.model, 'stream': True, 'stream_options': {'include_usage': True},
            'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user_text}],
            'max_completion_tokens': min(max_tokens, self.MAX_OUTPUT)}
    if self.reasoning_effort:
        body['reasoning_effort'] = self.reasoning_effort
    data = json.dumps(body).encode()
    for attempt in range(self.max_retries + 1):
        req = urllib.request.Request(self.url, data=data, headers={
            'Content-Type': 'application/json', 'Authorization': f'Bearer {self.key}', 'Accept': 'text/event-stream'})
        parts, usage, finish = [], {}, None
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                for raw in r:
                    line = raw.decode('utf-8', errors='replace').strip()
                    if not line.startswith('data:'):
                        continue
                    payload = line[5:].strip()
                    if payload == '[DONE]':
                        break
                    ev = json.loads(payload)
                    if ev.get('usage'):
                        usage = ev['usage']
                    for ch in ev.get('choices') or []:
                        parts.append((ch.get('delta') or {}).get('content') or '')
                        finish = ch.get('finish_reason') or finish
            u = usage or {}
            return ''.join(parts), {'turns': 1, 'prompt_tokens': u.get('prompt_tokens', 0),
                                    'output_tokens': u.get('completion_tokens', 0),
                                    'cache_hit_tokens': (u.get('prompt_tokens_details') or {}).get('cached_tokens', 0),
                                    'reasoning_tokens': (u.get('completion_tokens_details') or {}).get('reasoning_tokens', 0),
                                    'finish_reason': finish, 'stream': True}
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors='replace')[:500]
            if e.code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                time.sleep(min(2 ** attempt * 5, 60))   # 中转站短时不可用：最长约 20 分钟
                continue
            raise RuntimeError(f'OpenAI 接口错误 {e.code}：{detail}') from e
        except (urllib.error.URLError, http.client.HTTPException, ConnectionError, TimeoutError) as e:
            if attempt < self.max_retries:
                time.sleep(min(2 ** attempt * 5, 60))   # 中转站短时不可用：最长约 20 分钟
                continue
            raise RuntimeError(f'无法连接 OpenAI 接口（{self.url}）：{e}') from e


OpenAIBackend.complete = _openai_complete_stream


def make_backend(provider, model=None, think=False, timeout=600):
    """按服务商构造后端：deepseek | openai。"""
    if provider == 'openai':
        return OpenAIBackend(model=model or 'gpt-4.1', timeout=timeout)
    return DeepSeekBackend(model=model or 'deepseek-flash', think=think, timeout=timeout)

