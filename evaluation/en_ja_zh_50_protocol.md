# EN/JA → 简体中文：50 条本机对照协议

测试开始前固定输入、参考译文和审阅要点。25 条英语、25 条日语，包含 8 条 AI 药物发现文本
（英语 5、日语 3）。均为本次撰写的合成文本，不读取私人论文，也不复制公共评测集。
同一组 50 条输入逐一交给四个模型，总计 200 条正式结果；下载/接口预检另记，不计入正式分母。

候选配置：现有 `huihui_ai/hunyuan-mt-abliterated:7b-chimera` Q4_K_M；官方
Hy-MT2-1.8B GGUF Q8_0；MiLMMT-46-4B-v1.0 社区 GGUF Q4_K_M；Ollama 官方库
`translategemma:4b`。这是可在当前机器使用的四种配置的对照，不是相同量化精度下的架构消融。

| 项目 | 固定规则 |
| --- | --- |
| 目标语言 | 简体中文；已知源语言为 English 或 Japanese |
| 上下文 / 输出上限 | 全部 num_ctx=8192、num_predict=4096；每例独立请求、不携带前例历史 |
| 基线 | 当前 LingoFlow 的系统提示词和 auto 源语言提示词，temperature=0.1；保留真实使用配置，源语言仍由模型识别 |
| Hy-MT2 | 官方单轮 user 模板，无 system；temperature=0.7、top_p=0.6、top_k=20、repeat_penalty=1.05 |
| MiLMMT | 官方纯文本提示格式，raw completion，无 chat 包装；greedy |
| TranslateGemma | 官方带源/目标语言代码的 user 提示词，保留要求的空行；greedy |
| 随机数 | seed=42；单轮结果不代表多种采样种子的平均水平 |
| 顺序 | 模型逐个运行；每个模型 E01、J01、E02、J02……E25、J25，首次请求单独记冷启动 |
| 资源 | 单个被测模型驻留；只卸载本次评测的模型；记录 Ollama /api/ps 的 size/size_vram，不等同整个系统或进程峰值 RSS |
| 重试 | 正式测试不静默重试；保留错误、截断与空响应，失败仍占 50 条分母 |
| 速度 | 首个非空输出延迟、总耗时、Ollama 加载/预填充/生成耗时与 token 数；冷启动与后续请求分列 |
| 质量 | 每条按原文/检查点审阅，0–4 分。≥3 为可直接阅读或只有轻微问题；≤2 需实质修正 |

审阅时把每条输出替换成随机编号，隐藏模型名后由本次助手逐条审阅，再解码汇总。
这不是独立专业人工双盲 MQM；评分保留逐条理由和关键错误示例，供用户复核。
字面数值/占位符检查仅用于发现可疑项，不自动判定翻译对错。E25/J25 的参考中文为提要，
完整性需对照完整原文，不把提要当逐字金标准。50 条定向测试用于本人的选型，不能外推全球排名。

提示格式依据：

- [Hy-MT2 官方模型与推理参数](https://huggingface.co/tencent/Hy-MT2-1.8B)
- [Hy-MT2 官方单轮模板](https://huggingface.co/tencent/Hy-MT2-1.8B/blob/main/chat_template.jinja)
- [MiLMMT 官方使用说明](https://github.com/xiaomi-research/gemmax#-translation-prompt)
- [TranslateGemma 的 Ollama 提示格式](https://ollama.com/library/translategemma)

预检发现 Hy-MT2 的 HF→Ollama 自动转换模板缺少 user 内容且含残缺文本 `onse }}`。
正式对照使用官方完整单轮模板进行 raw 请求，并显式设置结束符；不会用损坏模板的输出来评判模型。
其他模型也先检查导入模板。完整请求、模板来源、模型 digest、结束原因与原始输出会保存在结果中。
