/** A classic two-tone ring (400 + 450 Hz, ring-ring then a pause), made in the browser. */
export function startRingtone(): () => void {
  const context = new AudioContext()
  const gain = context.createGain()
  gain.gain.value = 0
  gain.connect(context.destination)
  for (const frequency of [400, 450]) {
    const oscillator = context.createOscillator()
    oscillator.frequency.value = frequency
    oscillator.connect(gain)
    oscillator.start()
  }

  function ring() {
    const now = context.currentTime
    for (const offset of [0, 0.6]) {
      gain.gain.setValueAtTime(0.08, now + offset)
      gain.gain.setValueAtTime(0, now + offset + 0.4)
    }
  }
  ring()
  const timer = window.setInterval(ring, 3000)

  return () => {
    window.clearInterval(timer)
    void context.close()
  }
}
