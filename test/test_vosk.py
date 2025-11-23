import pyaudio
import numpy as np
import json
from vosk import Model, KaldiRecognizer
from samplerate import resample

model_path = "/opt/vosk_service/vosk-model-small-cn-0.3"

INPUT_RATE = 48000  # 麦克风实际采样率
MODEL_RATE = 16000  # Vosk 模型要求采样率
CHANNELS = 1
CHUNK = 48000  # 每次读 1 秒数据（可调小如 24000）

model = Model(model_path)
rec = KaldiRecognizer(model, MODEL_RATE)

p = pyaudio.PyAudio()
stream = p.open(
    format=pyaudio.paInt16,
    channels=CHANNELS,
    rate=INPUT_RATE,
    input=True,
    frames_per_buffer=CHUNK,
    input_device_index=2  # 对应 hw:2,0
)

print("🎙️ 请说话（使用 48kHz 麦克风 + 实时降采样）...")

buffer = []
try:
    while True:
        # 读取原始 48kHz 音频
        data = stream.read(CHUNK, exception_on_overflow=False)
        audio_data = np.frombuffer(data, dtype=np.int16)

        # 降采样到 16kHz
        ratio = MODEL_RATE / INPUT_RATE  # 16000 / 48000 = 1/3
        resampled = resample(audio_data, ratio, 'sinc_best')  # 或 'sinc_medium'

        # 转回 bytes 供 Vosk 使用
        resampled_bytes = resampled.astype(np.int16).tobytes()

        # 送入 Vosk
        if rec.AcceptWaveform(resampled_bytes):
            result = json.loads(rec.Result())
            text = result.get("text", "").strip()
            if text:
                print("✅ 识别结果:", text)

except KeyboardInterrupt:
    print("\n🛑 停止识别")
finally:
    stream.stop_stream()
    stream.close()
    p.terminate()
