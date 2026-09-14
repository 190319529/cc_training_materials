# cc_training_materials

本机 Web 版 YOLO 数据标注、训练和自动标注工作台，不依赖 Qt。

## 启动

```bash
cd /hdd/material
./start_cc_training_materials.sh
```

本机地址：`http://127.0.0.1:8765`

局域网地址：`http://172.10.20.34:8765`

启动脚本默认监听局域网地址。如需限制为仅本机访问：

```bash
./start_cc_training_materials.sh --host 127.0.0.1 --port 8765
```

服务允许读写本机路径。只应在可信网络使用 `0.0.0.0`，不要直接暴露到公网。

## 当前项目

项目目录：`/hdd/material/cc_training_materials_dataset`

已挂载两个图片源，不复制原图：

- `/hdd/mp4/Coaxial-drone_4fps_png_images`：657 张
- `/hdd/mp4/drone_clips_combined_no_audio_4fps_png_images`：225 张

标签按来源分别保存在：

```text
cc_training_materials_dataset/
├── labels/
│   ├── Coaxial-drone_4fps_png_images/
│   └── drone_clips_combined_no_audio_4fps_png_images/
├── .cc_training_materials.json
└── cc_training_materials.yaml       # 开始训练时生成
```

添加外部图片时，可以在“添加图片目录”窗口同时选择“外部标注目录”。程序会按图片的相对路径寻找同名 `.txt`，例如：

```text
图片目录/frame_001.png
标注目录/frame_001.txt
```

不选择外部标注目录时，标签仍保存到项目的 `labels/` 目录。来源配置会记录在 `.cc_training_materials.json` 中。

## 工作流

1. 打开项目，在类别编辑器中修改编号和名称，使用“添加类别”或删除按钮维护类别；编号必须从 `0` 开始连续排列，然后保存类别配置。
2. 先标注具有代表性的图片。没有目标的负样本也要保存，生成空的 `.txt` 标签。
3. 选择预训练 `.pt`，先用“预标注当前图片”检查模型、类别 ID 和置信度是否正确。
4. 人工样本达到要求后训练。程序按固定随机种子划分训练集和验证集，结果写入项目的 `runs/cc_training_materials_时间/`。
5. 用训练生成的 `weights/best.pt` 批量自动标注。默认跳过已有标签；覆盖模式会先备份旧标签。
6. 在“待复核”中逐张修正，并保存为已复核。

训练页支持晴天、大太阳、多云、乌云、雾天、雨天、雪天和夜间素材增强。新增比例是相对真实训练图片总数的比例；增强图只写入临时训练视图，不修改原图，也不会进入验证集。尚未复核的模型标签会自动排除在训练数据之外。

常用快捷键：数字 `1`、`2` 选择类别 0、1；`Delete` 删除选中的框；`D` 将当前图片移入项目回收目录；`Enter` 或空格保存标签并进入下一张。

## 建议

- 首批人工样本应覆盖距离、尺度、角度、光照、遮挡和复杂背景，而不是只取连续相邻帧。
- 保留适量无目标图片作为负样本，减少模型在背景上的误检。
- 类别 ID 一旦开始标注不要改变含义。修改或交换编号时，程序会按类别名称迁移已有标签并保留备份；删除仍被标签使用的类别会被拒绝。模型输出类别必须与页面类别配置一致。
- 少量数据可验证流程，但稳定模型通常需要更多独立场景。相邻视频帧高度相似，不能等同于同数量的独立样本。
- 训练集和验证集最好来自不同视频片段。当前自动划分以图片为单位；正式评估时建议按视频来源手工隔离验证集。
- 批量标注后必须人工复核。置信度较低有利于减少漏标，但会增加复核量。

## 测试

```bash
cd /hdd/material
python3 -m unittest -v test_cc_training_materials.py
```
