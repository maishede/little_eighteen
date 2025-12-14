import pyaudio
p = pyaudio.PyAudio()
print("\n====== 设备列表 ======")
for i in range(p.get_device_count()):
    try:
        info = p.get_device_info_by_index(i)
        # 你的麦克风名字里应该包含 "USB"
        if "USB" in info['name']:
            print(f"✅ 推荐 -> Index {i}: {info['name']} (MaxInput: {info['maxInputChannels']})")
        else:
            print(f"   Index {i}: {info['name']}")
    except:
        pass
print("======================\n")