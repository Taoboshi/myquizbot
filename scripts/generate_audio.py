import math
import struct
import base64

def make_wav(samples, sample_rate=22050):
    num_samples = len(samples)
    byte_rate = sample_rate * 2
    block_align = 2
    subchunk2_size = num_samples * 2
    chunk_size = 36 + subchunk2_size
    header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF', chunk_size, b'WAVE',
        b'fmt ', 16, 1, 1, sample_rate, byte_rate, block_align, 16,
        b'data', subchunk2_size
    )
    data = bytearray(header)
    for s in samples:
        val = max(-32767, min(32767, int(s * 32767)))
        data.extend(struct.pack('<h', val))
    return 'data:audio/wav;base64,' + base64.b64encode(data).decode('ascii')

sr = 22050
samples_c = []
for i in range(int(sr * 0.09)):
    t = i / sr
    env = math.exp(-t * 30)
    samples_c.append(0.35 * math.sin(2 * math.pi * 587.33 * t) * env)
for i in range(int(sr * 0.16)):
    t = i / sr
    env = math.exp(-t * 20)
    samples_c.append(0.40 * math.sin(2 * math.pi * 880.00 * t) * env)

samples_w = []
for i in range(int(sr * 0.18)):
    t = i / sr
    freq = 190 - (70 * (t / 0.18))
    env = math.exp(-t * 15)
    samples_w.append(0.30 * math.sin(2 * math.pi * freq * t) * env)

wav_c = make_wav(samples_c, sr)
wav_w = make_wav(samples_w, sr)

with open('scripts/audio_constants.py', 'w', encoding='utf-8') as f:
    f.write(f'AUDIO_CORRECT = "{wav_c}"\n')
    f.write(f'AUDIO_WRONG = "{wav_w}"\n')
print("Successfully generated audio_constants.py")
