import torch
import soundfile as sf
import time
from qwen_tts import Qwen3TTSModel
import sounddevice as sd

model = Qwen3TTSModel.from_pretrained(
    r"E:\Qwen3-TTS\Qwen3-TTS-12Hz-1.7B-Base",
    device_map="cuda:0",
    dtype=torch.bfloat16
)

ref_audio = "./models/mika_ref.mp3"
ref_text = "咦？老师认真工作的时候，原来是这种感觉啊。"

prompt_items = model.create_voice_clone_prompt(
    ref_audio=ref_audio,
    ref_text=ref_text,
    x_vector_only_mode=False,
)

while True:
    text = input("Enter text to synthesize (or 'exit' to quit): ")
    if text.lower() == 'exit':
        break

    t1 = time.time()
    wavs, sr = model.generate_voice_clone(
        text=text,
        language="auto",
        voice_clone_prompt=prompt_items
    )
    t2 = time.time()
    print(f"Generation time: {t2 - t1:.2f} seconds")
    # sd.play(wavs[0], sr)
    # sd.wait()
    sf.write("mika.wav", wavs[0], sr)
