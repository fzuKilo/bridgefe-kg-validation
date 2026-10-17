"""本地开源模型驱动层（Ollama），用于小模型与跨基座比较（论文 H2）。

与 Claude 驱动层共用系统提示词与工具定义，经 Ollama REST 接口 /api/chat 调用，
不依赖额外 Python 包。小模型上下文有限：较早的工具结果会被截短，只保留最近若干轮的完整内容。
"""
import json
import urllib.error
import urllib.request

from .claude import MAX_NUDGES, MAX_TURNS, SYSTEM_PROMPT, TOOLS

DEFAULT_LOCAL_MODEL = 'qwen3.5:9b'
KEEP_FULL = 24          # 保留完整内容的最近消息数
TRUNCATE_TO = 300       # 更早的工具结果截短到的字符数

OLLAMA_TOOLS = [{'type': 'function',
                 'function': {'name': t['name'], 'description': t['description'],
                              'parameters': t['input_schema']}} for t in TOOLS]


class OllamaDriver:
    def __init__(self, session, model=DEFAULT_LOCAL_MODEL, host='http://localhost:11434',
                 num_ctx=32768, think=True, timeout=900):
        self.s = session
        self.model = model
        self.url = host.rstrip('/') + '/api/chat'
        self.options = {'num_ctx': num_ctx}
        self.think = think
        self.timeout = timeout
        self.usage = {'prompt_tokens': 0, 'output_tokens': 0, 'turns': 0, 'model': model}

    def _chat(self, messages):
        body = json.dumps({'model': self.model, 'messages': messages, 'tools': OLLAMA_TOOLS,
                           'stream': False, 'think': self.think, 'options': self.options}).encode()
        req = urllib.request.Request(self.url, data=body, headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read())
        except urllib.error.URLError as e:
            raise RuntimeError(f'无法连接 Ollama（{self.url}）：{e}。请先运行 `ollama serve` 并拉取模型 '
                               f'`ollama pull {self.model}`') from e

    def _compact(self, messages):
        """截短较早的工具结果，控制上下文长度。"""
        for m in messages[1:-KEEP_FULL]:
            if m['role'] == 'tool' and len(m['content']) > TRUNCATE_TO:
                m['content'] = m['content'][:TRUNCATE_TO] + ' …(truncated)'

    def _dispatch(self, name, args):
        fn = getattr(self.s, name, None)
        if fn is None or name not in {t['name'] for t in TOOLS}:
            return {'error': f'unknown tool {name}'}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                return {'error': f'arguments for {name} are not valid JSON'}
        try:
            return fn(**(args or {}))
        except TypeError as e:
            return {'error': f'invalid arguments for {name}: {e}'}

    def run(self, description):
        messages = [{'role': 'system', 'content': SYSTEM_PROMPT},
                    {'role': 'user', 'content': f'Bridge description:\n\n{description}'}]
        nudges = 0
        for _ in range(MAX_TURNS):
            self._compact(messages)
            resp = self._chat(messages)
            self.usage['turns'] += 1
            self.usage['prompt_tokens'] += resp.get('prompt_eval_count', 0)
            self.usage['output_tokens'] += resp.get('eval_count', 0)
            msg = resp['message']
            calls = msg.get('tool_calls') or []
            messages.append({'role': 'assistant', 'content': msg.get('content', ''),
                             **({'tool_calls': calls} if calls else {})})
            if not calls:
                if self.s.done or nudges >= MAX_NUDGES:
                    break
                nudges += 1
                messages.append({'role': 'user', 'content': 'The session is not finished. Continue the workflow '
                                 'by calling tools; call finish once generate_model has succeeded.'})
                continue
            for c in calls:
                fn = c.get('function', {})
                out = self._dispatch(fn.get('name'), fn.get('arguments'))
                messages.append({'role': 'tool', 'tool_name': fn.get('name'),
                                 'content': json.dumps(out, ensure_ascii=False, default=str)})
            if self.s.done:
                break
        self.usage['finished'] = self.s.done
        return self.usage
