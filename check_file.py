with open('code_puppy/themes/theme.py', 'r') as f:
    lines = f.readlines()
    print(f'Total lines: {len(lines)}')
    print('Last 10 lines:')
    for line in lines[-10:]:
        print(repr(line))
