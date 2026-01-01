import re

KANJI_MAP = {
    '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
    '六': 6, '七': 7, '八': 8, '九': 9,
    '壱': 1, '弐': 2, '参': 3 
}
UNIT_MAP = {
    '十': 10, '百': 100, '千': 1000, '万': 10000
}

def kanji_to_int(text: str) -> int:
    """
    Convert a Japanese Kanji numeral string to an integer.
    Simple implementation for typical law numbering (handling up to thousands/man).
    """
    if not text:
        return 0
    if text.isdigit():
        return int(text)
    
    total = 0
    current = 0
    
    # Simple parser: iterate chars.
    # If 1-9, set current.
    # If unit, mult current (or 1) by unit and add to total.
    # If end, add current.
    
    # E.g. 二十三 -> 2, 10 -> 20 + 3 -> 23
    # 十三 -> 10 + 3 -> 13
    # 百二 -> 100 + 2 -> 102
    
    # Need to handle case where unit starts (e.g. 十 -> 10)
    
    for char in text:
        if char in KANJI_MAP:
            current = KANJI_MAP[char]
        elif char in UNIT_MAP:
            unit = UNIT_MAP[char]
            if current == 0:
                current = 1
            total += current * unit
            current = 0
        else:
            # Valid digit chars only? For PoC, ignore or break?
            # Assuming input is clean kanji numeral
            pass
            
    total += current
    return total
