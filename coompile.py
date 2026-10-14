import pathlib

def assemble_python_project(root_dir, output_file):
    root = pathlib.Path(root_dir)
    output_path = pathlib.Path(output_file)
    
    with open(output_path, 'w', encoding='utf-8') as outfile:
        # Рекурсивно ищем все .py файлы
        for py_file in root.rglob('*.py'):
            # Пропускаем сам файл вывода, если он находится в той же папке
            if py_file.resolve() == output_path.resolve():
                continue
            
            # Пропускаем папки виртуального окружения и кэша
            if any(part in py_file.parts for part in ['venv', '.venv', '__pycache__', 'env']):
                continue

            # Получаем относительный путь для красоты
            relative_path = py_file.relative_to(root)
            
            outfile.write(f"{'='*80}\n")
            outfile.write(f"FILE: {relative_path}\n")
            outfile.write(f"{'='*80}\n\n")
            
            try:
                content = py_file.read_text(encoding='utf-8')
                outfile.write(content)
            except Exception as e:
                outfile.write(f"ERROR READING FILE: {e}")
            
            outfile.write("\n\n")

    print(f"Готово! Весь код собран в: {output_file}")

# Запуск: '.' означает текущую папку, 'full_code.txt' — имя итогового файла
assemble_python_project('.', 'all_my_code.txt')