"""음계와 음높이 계산."""

SCALES = {
    'chromatic': [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
    'major': [0, 2, 4, 5, 7, 9, 11],
    'minor': [0, 2, 3, 5, 7, 8, 10],
    'dorian': [0, 2, 3, 5, 7, 9, 10],
    'majorpentatonic': [0, 2, 4, 7, 9],
    'minorpentatonic': [0, 3, 5, 7, 10],
    'wholetone': [0, 2, 4, 6, 8, 10],
    'hirajoshi': [0, 2, 3, 7, 8],
}
SCALE_KEYS = list(SCALES.keys())
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


def quantize(midi, scale='majorpentatonic', root=0):
    """MIDI 음을 음계 안의 가장 가까운 음으로. 같은 거리면 낮은 음."""
    steps = SCALES.get(scale, SCALES['chromatic'])
    r = int(round(midi))
    best, best_d = r, float('inf')
    for octave in (-1, 0, 1):
        base = ((r - root) // 12) * 12 + root + octave * 12
        for s in steps:
            c = base + s
            d = abs(c - midi)
            if d < best_d or (d == best_d and c < best):
                best, best_d = c, d
    return int(best)


def band_notes(n, low=36, high=96, scale='majorpentatonic', root=0):
    """n 개 대역(아래→위)에 줄 MIDI 음. 낮은 대역 = 낮은 음."""
    if n <= 1:
        return [quantize((low + high) / 2.0, scale, root)]
    return [quantize(low + (high - low) * i / (n - 1), scale, root) for i in range(n)]


def note_name(midi):
    midi = int(round(midi))
    return '%s%d' % (NOTE_NAMES[midi % 12], midi // 12 - 1)


def midi_to_freq(midi):
    return 440.0 * 2 ** ((midi - 69) / 12.0)
