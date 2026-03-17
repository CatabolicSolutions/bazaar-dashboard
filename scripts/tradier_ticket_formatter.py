import sys
from tradier_board_utils import build_board, parse_raw_tickets


def main():
    raw = sys.stdin.read()
    tickets = parse_raw_tickets(raw)
    print(build_board(tickets))


if __name__ == '__main__':
    main()
