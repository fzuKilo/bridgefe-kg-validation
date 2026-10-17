"""消融开关（论文 3.6 节 A1–A6；A6 为单智能体，由 --agents single 实现）。

  A1 去掉决策级数值校验（含单位、复算结果反馈与依赖复核）；模型级校核保留
  A1P（论文 A1+）在 A1 基础上再去掉模型级 L2-1 复算，即完全没有数值校验
  A2 去掉依据存在性与条件适用性校验
  A3 去掉一致性与实例约束（C-01~C-08 实例约束、C-11/C-12/C-13/C-15 一致性）；前置决策顺序（C-14）保留
  A4 反馈只保留“拒绝”，不给违反的校验、公式结果与可用依据
  A5 不做溯源定位：模型级校核只给违反的校核编号与约束条文，不给可疑决策
  NOVAL 提案照单接受、NOCHECK 不做模型级 L1–L3 校核（基线 C2–C4，见 agent/baselines.py）
  F0 仅告知失败：模型级校核只说明模型未通过（注入错误实验的对照信号）
  DEFECT 边界输入实验：给智能体增加 report_input_defect 工具，并在提示词中说明何时使用（C4、C5 同等提供）
"""
ACTIVE = set()


def on(name):
    return name in ACTIVE


def set_active(names):
    ACTIVE.clear()
    ACTIVE.update(n for n in names if n)
