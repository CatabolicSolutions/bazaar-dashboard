#!/usr/bin/env python3
import re
import sys

def condense_board(board_path):
    with open(board_path, 'r') as f:
        lines = f.readlines()
    
    output = []
    i = 0
    vix = 'N/A'
    # find VIX line
    for line in lines:
        if line.startswith('VIX:'):
            vix = line.strip().split(': ')[1]
            break
    
    output.append('BAZAAR OF FORTUNES — TRADIER LEADERS BOARD')
    output.append(f'VIX: {vix}')
    
    # find sections
    section = None
    leaders = []
    current_leader = None
    leader_lines = []
    
    while i < len(lines):
        line = lines[i].rstrip()
        if line == 'Directional / Scalping Leaders':
            section = 'scalping'
            output.append('\nDirectional / Scalping Leaders')
            i += 1
            continue
        elif line == 'Premium / Credit Leaders':
            section = 'credit'
            output.append('\nPremium / Credit Leaders')
            i += 1
            continue
        elif line.startswith('Run Notes'):
            break
        
        # detect leader line like "1. NVDA PUT | Underlying ..."
        if section and re.match(r'^\d+\.\s+[A-Z]+ (CALL|PUT)', line):
            # store previous leader
            if current_leader is not None:
                leaders.append((current_leader, leader_lines))
            current_leader = line
            leader_lines = [line]
        elif current_leader is not None and line.startswith('   ') and not line.startswith('   Candidate ID:'):
            # capture thesis, entry, etc
            leader_lines.append(line.strip())
        i += 1
    
    if current_leader is not None:
        leaders.append((current_leader, leader_lines))
    
    # output leaders with condensation
    for idx, (leader, extra) in enumerate(leaders):
        if idx < 2:
            output.append(leader)
            # output only confidence and risk lines if present
            for ex in extra:
                if 'Confidence:' in ex:
                    output.append(f'   {ex}')
                elif 'Risk:' in ex:
                    output.append(f'   {ex}')
        else:
            output.append(leader)
    
    # run notes
    run_start = None
    for j, line in enumerate(lines):
        if line.startswith('Run Notes'):
            run_start = j
            break
    if run_start is not None:
        output.append('\nRun Notes')
        for j in range(run_start + 1, len(lines)):
            l = lines[j].rstrip()
            if l == '':
                continue
            if l.startswith('-'):
                output.append(l)
            else:
                break
    
    # operator framing (hardcoded)
    output.append('\nOperator framing')
    if any('Scalping' in str(leaders) for leader, _ in leaders):
        output.append('- Directional setups are present; only engage if momentum confirms and structure is clean')
    if any('Credit' in str(leaders) for leader, _ in leaders):
        output.append('- Premium setups are present; treat as defined-risk spreads, not naked premium selling')
    output.append('- If entries require chasing, spreads widen, or vol regime shifts against entry, stand down.')
    
    return '\n'.join(output)

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Usage: condense_board.py <board_file>')
        sys.exit(1)
    print(condense_board(sys.argv[1]))