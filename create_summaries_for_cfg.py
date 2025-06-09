import argparse
import pandas as pd
import re
from collections import defaultdict
from pathlib import Path
from openpyxl import Workbook

# Utility: extract content inside a function block with possible nested braces
def extract_function_block(content, func_pattern):
    match = re.search(func_pattern, content)
    if not match:
        return None
    brace_start = match.end()
    brace_count = 1
    end = brace_start
    while end < len(content) and brace_count:
        if content[end] == '{':
            brace_count += 1
        elif content[end] == '}':
            brace_count -= 1
        end += 1
    return content[brace_start:end - 1]

# Utility: parse a single cfg file into a list of functors with their properties
def parse_cfg(file_path):
    functors = []
    current = None

    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('[') and line.endswith(']'):
                functor_name = line[1:-1].strip()
                if '::' in functor_name or functor_name.lower() == 'analytics':
                    current = None
                    continue
                current = {'name': functor_name, 'file': str(file_path), 'props': {}}
                functors.append(current)
            elif '=' in line and current is not None:
                k, v = map(str.strip, line.split('=', 1))
                if k not in current['props']:
                    current['props'][k] = v
    return functors

# Extract properties from a cpp implementation file
def parse_cpp_properties(cpp_path):
    content = Path(cpp_path).read_text()
    init_pattern = r'\b\w+::\s*init\s*\([^)]*\)\s*\{'
    init_block = extract_function_block(content, init_pattern)
    if not init_block:
        return []

    setting_pattern = re.findall(
        r'vm->Get\w+Setting\s*\(\s*m_cfgTag\s*\+\s*"\\.([^"\']+)"\s*(?:,\s*([\w\.\-]+|\"[^\"]*\"|\'[^\']*\'))?\)',
        init_block,
        re.DOTALL
    )

    properties = []
    for prop_name, default_value in setting_pattern:
        properties.append((prop_name, default_value.strip() if default_value else ''))

    return properties

# Extract calculator registrations and property defaults
def parse_register_cpp(cpp_files):
    cpp_map = defaultdict(list)
    cpp_prop_defaults = defaultdict(list)

    for cpp_file in cpp_files:
        if 'register' in cpp_file.name.lower():
            content = Path(cpp_file).read_text()
            reg_block = re.search(r'Register\(\)\s*\{\s*(.*?)\s*\}', content, re.DOTALL)
            if not reg_block:
                continue
            registrations = re.findall(
                r'Registrator<\s*Calculator\s*>.*?"([^"]+)"\s*,\s*ObjectFactory<\s*Calculator\s*>::DFactoryMethod<\s*([^>\s]+)\s*>',
                reg_block.group(1),
                re.DOTALL
            )
            for reg_type, class_name in registrations:
                cpp_map[str(cpp_file)].append((reg_type, class_name))

    class_lookup = {cls: reg for cpp_entries in cpp_map.values() for reg, cls in cpp_entries}
    for cpp_file in cpp_files:
        if 'register' in cpp_file.name.lower():
            continue
        class_name = cpp_file.stem
        props = parse_cpp_properties(cpp_file)
        if class_name in class_lookup:
            cpp_prop_defaults[class_name].extend(props)

    return cpp_map, cpp_prop_defaults

# Group by calculator type and gather metadata
def group_by_calculator(functors):
    calculators = defaultdict(lambda: {'files': set(), 'functors': []})

    for f in functors:
        if 'type' in f['props']:
            calc_type = f['props']['type']
            calculators[calc_type]['files'].add(f['file'])
            calculators[calc_type]['functors'].append(f)

    return calculators

# Build output Excel file
def write_summary(calculators, output_file, cpp_map, cpp_prop_defaults):
    output_file = Path(output_file)
    if output_file.exists():
        output_file.unlink()

    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        for calc, data in calculators.items():
            sorted_files = sorted(data['files'])
            relative_paths = [f.split("m5-ccfa2.0/", 1)[-1] if "m5-ccfa2.0/" in f else f for f in sorted_files]
            used_in_df = pd.DataFrame(relative_paths, columns=['CFG Files'])

            default_dict = dict(cpp_prop_defaults.get(calc, []))
            list_props_df = pd.DataFrame({
                'Property Name': list(default_dict.keys()),
                'Default Value': list(default_dict.values())
            })

            all_props = sorted(set(p for f in data['functors'] for p in f['props'].keys()) - {'type', 'cashflow'})
            props = sorted(p for p in all_props if p != 'outputname')

            file_short_map = {f: Path(f).name for f in sorted_files}
            unique_rows = {}
            for f in data['functors']:
                row_key = tuple(f['props'].get(p, '') for p in props)
                if row_key not in unique_rows:
                    base_row = {p: f['props'].get(p, '') for p in props}
                    base_row['Cashflow'] = f['props'].get('cashflow', '')
                    base_row['Name'] = f['name']
                    for short in file_short_map.values():
                        base_row[short] = ''
                    unique_rows[row_key] = base_row
                short_name = file_short_map[f['file']]
                unique_rows[row_key][short_name] = 'X'

            all_columns = ['Cashflow', 'Name'] + props + list(file_short_map.values())
            out_df = pd.DataFrame(list(unique_rows.values()))[all_columns]
            out_df = out_df.dropna(subset=['Name'])
            if out_df.empty:
                continue
            out_df.sort_values(by=['Cashflow', 'Name'], inplace=True)

            sheetname = str(calc)[:31]
            start = 0
            used_in_df.to_excel(writer, sheet_name=sheetname, index=False, startrow=start)
            start += len(used_in_df) + 2
            list_props_df.to_excel(writer, sheet_name=sheetname, index=False, startrow=start)
            start += len(list_props_df) + 2
            out_df.to_excel(writer, sheet_name=sheetname, index=False, startrow=start)

        calc_rows = []
        for cpp_file, registrations in cpp_map.items():
            for reg_name, tab_name in registrations:
                row = {
                    'Tab': Path(cpp_file).name,
                    'Calculator Name': tab_name,
                    'Type': reg_name,
                    'Description': ''
                }
                calc_rows.append(row)

        if calc_rows:
            summary_df = pd.DataFrame(calc_rows, columns=['Tab', 'Calculator Name', 'Type', 'Description'])
            summary_df.to_excel(writer, sheet_name='calculator summary', index=False)

# Main driver
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--infile', required=True, help='Input .cfg file or .csv with paths')
    parser.add_argument('-o', '--outfile', default='./cfg_summary.xlsx', help='Output .xlsx file')
    parser.add_argument('-c', '--cpp', help='Optional .csv with list of .cpp files')
    args = parser.parse_args()

    input_path = Path(args.infile)
    cfg_files = []
    if input_path.suffix == '.cfg':
        cfg_files = [input_path]
    elif input_path.suffix == '.csv':
        with open(input_path, newline='') as csvfile:
            import csv
            reader = csv.reader(csvfile)
            for row in reader:
                if row:
                    path_str = row[0].strip().replace("PosixPath(", "").replace(")", "").replace("'", "").strip()
                    cfg_files.append(Path(path_str))
    else:
        raise ValueError("Input must be a .cfg file or a .csv listing .cfg files")

    all_functors = []
    for file in cfg_files:
        if file.exists():
            all_functors.extend(parse_cfg(file))

    grouped = group_by_calculator(all_functors)

    cpp_map, cpp_prop_defaults = {}, {}
    if args.cpp:
        cpp_list_path = Path(args.cpp)
        if cpp_list_path.exists():
            import csv
            with open(cpp_list_path) as f:
                reader = csv.reader(f)
                cpp_files = [Path(row[0].strip()) for row in reader if row]
            cpp_map, cpp_prop_defaults = parse_register_cpp(cpp_files)

    write_summary(grouped, args.outfile, cpp_map, cpp_prop_defaults)
    print(f"✅ Summary written to {args.outfile}")

if __name__ == '__main__':
    main()
