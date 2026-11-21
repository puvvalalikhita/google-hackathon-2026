class PCM16Processor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = [];
    this._targetRate = 16000;
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

    // Stream full unmodified 16kHz PCM audio (relying on Chrome AEC/NS + Gemini Live native VAD)
    const outLength = Math.floor(channelData.length / ratio);
    for (let i = 0; i < outLength; i++) {
      const idx = Math.floor(i * ratio);
      const s = Math.max(-1, Math.min(1, channelData[idx]));
      this._buffer.push(s < 0 ? s * 0x8000 : s * 0x7fff);
    }

    // Emit chunks of 1600 samples (100ms at 16kHz) for low latency
    if (this._buffer.length >= 1600) {
      const int16 = new Int16Array(this._buffer.splice(0, 1600));
      this.port.postMessage(
        {
          pcm: int16.buffer,
          rms: rms,
        },
        [int16.buffer]
      );
    }
    return true;
  }
}

registerProcessor("pcm16-processor", PCM16Processor);
