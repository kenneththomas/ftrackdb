import sys
import os
import time

#take input of 4 4x400 splits ex 45.58 45.58 45.58 45.58 and add them up to minutes and seconds. also print each leg total time
def main():
    if len(sys.argv) != 5:
        print("Usage: 4b4.py <split1> <split2> <split3> <split4>")
        sys.exit(1)

    splits = [float(x) for x in sys.argv[1:]]
    total_time = sum(splits)
    minutes = int(total_time / 60)
    seconds = total_time % 60
    print(f"Total time: {minutes}:{seconds:.2f}")

# add each split time to the previous split time to get the intermediary times
    split_time = 0
    for split in splits:
        split_time += split
        minutes = int(split_time / 60)
        seconds = split_time % 60
        print(f"{split} | {minutes}:{seconds:.2f}")

if __name__ == "__main__":
    main()