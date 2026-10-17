"""Read historical generated AutoRuns without carrying their inert filler."""

LEGACY_FILLER = b'# pad -- see PAD_TO: mode 7 overwrites but does not truncate\n'


def without_legacy_padding(data):
    """Remove only the known generated tail; refuse commands hidden after it."""
    at = data.find(LEGACY_FILLER)
    if at < 0:
        return data
    if at and data[at - 1:at] != b'\n':
        raise ValueError('AutoRun padding marker is not at a line boundary')
    tail = data[at:]
    while tail.startswith(LEGACY_FILLER):
        tail = tail[len(LEGACY_FILLER):]
    if tail and (not tail.endswith(b'\n') or set(tail[:-1]) - {ord('#')}):
        raise ValueError('AutoRun has unexpected content after its padding marker')
    return data[:at]
