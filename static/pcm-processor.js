class PCM16Processor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = [];
    this._targetRate = 16000;
    this._noiseFloor = 0.008;
    this._hangoverFrames = 0;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) return true;

    const channelData = input[0];
    const ratio = sampleRate / this._targetRate;

    let rmsSum = 0;
    for (let i = 0; i < channelData.length; i++) {
      rmsSum += channelData[i] * channelData[i];
    }
    const rms = Math.sqrt(rmsSum / channelData.length);

    // Adaptive ambient noise gate so continuous speaker-bleed noise (e.g. 78dB mandi demo audio)
    // does not block Gemini Live API's automatic end-of-speech (VAD) detection when the user pauses.
    const speechThreshold = Math.max(0.015, this._noiseFloor * 2.1);
    let isSpeech = false;
    if (rms > speechThreshold) {
      isSpeech = true;
      this._hangoverFrames = 140; // ~370ms hangover so word endings are never clipped
      this._noiseFloor = this._noiseFloor * 0.999 + rms * 0.001;
    } else if (this._hangoverFrames > 0) {
      isSpeech = true;
      this._hangoverFrames -= 1;
    } else {
      // Quiet / steady background hum -> track noise floor & gate cleanly to silence for crisp VAD
      this._noiseFloor = Math.min(0.035, this._noiseFloor * 0.97 + rms * 0.03);
    }

    const outLength = Math.floor(channelData.length / ratio);
    for (let i = 0; i < outLength; i++) {
      const idx = Math.floor(i * ratio);
      const s = isSpeech ? Math.max(-1, Math.min(1, channelData[idx])) : 0;
      this._buffer.push(s < 0 ? s * 0x8000 : s * 0x7fff);
    }

    // Emit chunks of ~1600 samples (~100ms at 16kHz) for low latency
    if (this._buffer.length >= 1600) {
      const int16 = new Int16Array(this._buffer.splice(0, 1600));
      this.port.postMessage(
        {
          pcm: int16.buffer,
          rms: isSpeech ? rms : 0.002,
        },
        [int16.buffer]
      );
    }
    return true;
  }
}

registerProcessor("pcm16-processor", PCM16Processor);
