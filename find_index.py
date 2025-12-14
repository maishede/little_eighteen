import pyaudio
p = pyaudio.PyAudio()
print("\n====== 当前环境设备列表 ======")
for i in range(p.get_device_count()):
    try:
        info = p.get_device_info_by_index(i)
        # 过滤掉无法录音的设备 (maxInputChannels > 0 才是麦克风)
        if info['maxInputChannels'] > 0:
            print(f"✅ 麦克风候选 -> Index {i}: {info['name']} (Ch: {info['maxInputChannels']}, Rate: {info['defaultSampleRate']})")
        else:
            print(f"   输出设备   -> Index {i}: {info['name']}")
    except:
        pass
print("=============================\n")