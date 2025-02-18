import argparse
from pathlib import Path
from document_processor import DocumentProcessor
from result_writer import ResultWriter
import time

def format_time(seconds):
    """Formatea el tiempo en un formato legible."""
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"

def progress_callback(current, total, file_path, status):
    """Muestra el progreso del procesamiento."""
    percentage = (current * 100) / total if total > 0 else 0
    file_name = file_path.name if file_path else "..."
    
    # Limpiar línea anterior
    print('\r' + ' ' * 100, end='\r')
    
    # Mostrar progreso actual
    progress_bar = f"[{'=' * int(percentage/2)}{' ' * (50-int(percentage/2))}]"
    print(f"\rProgreso: {progress_bar} {percentage:.1f}% ({current}/{total})", end='')
    print(f"\n\rArchivo actual: {file_name}")
    print(f"Estado: {status}\n", end='')

def main():
    parser = argparse.ArgumentParser(description='Buscar palabras clave en documentos.')
    parser.add_argument('--directory', '-d', required=True, help='Directorio para buscar')
    parser.add_argument('--keywords', '-k', required=True, nargs='+', help='Palabras clave para buscar')
    parser.add_argument('--output', '-o', default='resultados.xlsx', help='Archivo de salida Excel')
    
    args = parser.parse_args()
    
    processor = DocumentProcessor()
    writer = ResultWriter(args.output)
    
    try:
        print("Iniciando búsqueda de archivos...")
        start_time = time.time()
        
        # Contar archivos primero
        total_files, _ = processor.count_processable_files(Path(args.directory))
        print(f"Se encontraron {total_files} archivos para procesar.")
        
        # Procesar archivos
        results = list(processor.process_directory(
            Path(args.directory), 
            args.keywords,
            progress_callback
        ))
        
        # Escribir resultados
        print("\nEscribiendo resultados en Excel...")
        writer.write_results(results)
        
        # Mostrar resumen
        end_time = time.time()
        elapsed_time = format_time(end_time - start_time)
        print(f"\nBúsqueda completada en {elapsed_time}")
        print(f"Se procesaron {total_files} archivos")
        print(f"Se encontraron {len(results)} coincidencias")
        print(f"Resultados guardados en {args.output}")
        
    except Exception as e:
        print(f"\nError durante la ejecución: {str(e)}")

if __name__ == '__main__':
    main() 