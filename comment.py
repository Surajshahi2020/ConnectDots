import re
from pathlib import Path

def parse_comments(file_path):
    text = Path(file_path).read_text(encoding='utf-8')
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    comments = []
    i = 0
    while i < len(lines):
        # Try to detect a new comment block by timestamp pattern at the end
        # Heuristic: look ahead for lines ending with time-like token (e.g., '1d', '20h', '9m')
        if i + 1 < len(lines) and re.match(r'\d+[dhm]$', lines[i + 1]):
            # This line is likely the comment body
            # So the previous line(s) must be the author
            # But author may be multi-line? In your data, seems 1 line.
            # Let's assume author is at i, comment at i+1 is timestamp → not right.

            # Better: Look for timestamp line, then work backward
            pass

        i += 1

    # Simpler approach: split by known timestamp lines
    blocks = []
    current_block = []
    time_pattern = re.compile(r'\d+[dhm]$')  # e.g., 1d, 20h, 9m

    for line in lines:
        if time_pattern.match(line) or line in {'Reply', 'Edited'}:
            if current_block:
                blocks.append(current_block)
                current_block = []
            if time_pattern.match(line):
                current_block = [line]  # start new block with timestamp
        else:
            current_block.append(line)

    if current_block:
        blocks.append(current_block)

    # Now process blocks in reverse (since timestamp is first in block in this method)
    # But actually, in your data, structure is:
    # [Author]
    # [Comment lines...]
    # [timestamp]
    # [optional: "Reply", "Edited"]

    # So better: iterate and detect timestamp lines as separators

    comments = []
    buffer = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r'\d+[dhm]$', line):
            # This is a timestamp → end of a comment block
            # Go backward to extract author and comment
            # From start of buffer to -1 is comment, last non-meta line before timestamp is author?
            # But in your data: author is FIRST line of block
            if buffer:
                # First line = author (may include location)
                author = buffer[0]
                # Middle lines = comment (could be multiple)
                comment_lines = buffer[1:] if len(buffer) > 1 else ['']
                comment = '\n'.join(comment_lines).strip()
                comments.append({
                    'author': author,
                    'comment': comment,
                    'timestamp': line
                })
            buffer = []
        elif line not in {'Reply', 'Edited'}:
            buffer.append(line)
        # Skip "Reply" and "Edited"
        i += 1

    # Handle last block if file doesn't end with timestamp (unlikely in your case)
    if buffer:
        author = buffer[0] if buffer else ''
        comment = '\n'.join(buffer[1:]).strip() if len(buffer) > 1 else ''
        comments.append({
            'author': author,
            'comment': comment,
            'timestamp': 'unknown'
        })

    return comments

# --- Main execution ---
if __name__ == '__main__':
    file_path = 'data.txt'  # Change if your file has a different name
    try:
        data = parse_comments(file_path)
        for idx, comment in enumerate(data, 1):
            print(f"--- Comment {idx} ---")
            print(f"Author: {comment['author']}")
            print(f"Timestamp: {comment['timestamp']}")
            print(f"Comment:\n{comment['comment']}\n")
    except FileNotFoundError:
        print(f"❌ File '{file_path}' not found in the current directory.")