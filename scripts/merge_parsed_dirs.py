import argparse
import shutil
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge parsed OCR result directories.")
    parser.add_argument("input_dirs", nargs="+", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for input_dir in args.input_dirs:
        for source in sorted(input_dir.glob("*.parsed.json")):
            target = args.output_dir / source.name
            shutil.copy2(source, target)
            copied += 1
    print(f"copied={copied}")
    print(f"unique={len(list(args.output_dir.glob('*.parsed.json')))}")


if __name__ == "__main__":
    main()
