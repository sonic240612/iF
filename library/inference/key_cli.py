"""키 관리 CLI."""
from __future__ import annotations

import sys

from library.inference.key_manager import get_keys, add_keys, remove_key


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "list":
        keys = get_keys()
        print(f"등록된 키 {len(keys)}개:")
        for i, k in enumerate(keys, 1):
            print(f"  {i}. ...{k[-6:]}  ({k[:8]}...)")
    elif cmd == "add":
        if len(sys.argv) < 3:
            print("사용법: python -m library.inference.key_manager add KEY [KEY...]")
            sys.exit(1)
        keys = add_keys(*sys.argv[2:])
        print(f"추가 완료. 현재 {len(keys)}개 키 등록됨.")
    elif cmd == "remove":
        if len(sys.argv) < 3:
            print("사용법: python -m library.inference.key_manager remove KEY_OR_PREFIX")
            sys.exit(1)
        keys = remove_key(sys.argv[2])
        print(f"제거 완료. 현재 {len(keys)}개 키 등록됨.")
    else:
        print(f"알 수 없는 명령: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
