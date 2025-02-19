from flask import Flask, render_template, request, jsonify, send_file, abort, url_for
from flask_socketio import SocketIO, emit
from document_processor import DocumentProcessor
from models.firebase_manager import FirebaseManager
from pathlib import Path
import os
import threading
import time
from tkinter import filedialog, Tk
import tkinter as tk
import psutil

from datetime import datetime

app = Flask(__name__)
import os
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'fallback_key')

socketio = SocketIO(app)

firebase = FirebaseManager()

class SearchProgress:
    def __init__(self):
        self.start_time = None
        self.processed_files = 0
        self.total_files = 0

    def start(self, total_files):
        self.start_time = time.time()
        self.total_files = total_files
        self.processed_files = 0

    def update(self, current):
        self.processed_files = current

    def get_times(self):
        if not self.start_time:
            return "00:00:00", "00:00:00"

        elapsed = time.time() - self.start_time
        if self.processed_files == 0:
            return self.format_time(elapsed), "Calculando..."

        files_per_second = self.processed_files / elapsed
        remaining_files = self.total_files - self.processed_files
        estimated_remaining = remaining_files / files_per_second if files_per_second > 0 else 0

        return self.format_time(elapsed), self.format_time(estimated_remaining)

    @staticmethod
    def format_time(seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

search_progress = SearchProgress()

def progress_callback(current, total, file_path, status, file_progress=0):
    """Envía actualizaciones de progreso al cliente mediante WebSocket."""
    # Calcular el porcentaje general basado en archivos completados
    percentage = ((current - 1) * 100) / total if total > 0 else 0
    # Añadir la fracción del archivo actual
    if file_progress > 0:
        percentage += (file_progress / 100) * (100 / total)
    
    search_progress.update(current)
    elapsed, remaining = search_progress.get_times()
    
    socketio.emit('progress_update', {
        'percentage': round(percentage, 2),
        'current': current,
        'total': total,
        'file_name': file_path.name if file_path else "",
        'status': status,
        'file_progress': file_progress,
        'elapsed_time': elapsed,
        'remaining_time': remaining,
        'error': status if isinstance(status, str) and 'error' in status.lower() else None
    })

@app.route('/')
def index():
    try:
        # Obtener estadísticas del dashboard
        dashboard_data = firebase.get_dashboard_data()
        
        # Extraer estadísticas generales
        stats = dashboard_data.get('general_stats', {})
        
        # Si no hay estadísticas, usar valores por defecto
        if not stats:
            stats = {
                'total_searches': 0,
                'total_findings': 0,
                'total_files': 0,
                'avg_execution_time': 0
            }
        
        return render_template('index.html', stats=stats)
    except Exception as e:
        print(f"Error obteniendo estadísticas para index: {str(e)}")
        # Proporcionar valores por defecto en caso de error
        default_stats = {
            'total_searches': 0,
            'total_findings': 0,
            'total_files': 0,
            'avg_execution_time': 0
        }
        return render_template('index.html', stats=default_stats)

@app.route('/search', methods=['GET'])
def search():
    try:
        recent_searches = firebase.get_recent_searches()
        return render_template('search.html', recent_searches=recent_searches)
    except Exception as e:
        print(f"Error obteniendo búsquedas recientes: {str(e)}")
        return render_template('search.html', recent_searches=[])

@app.route('/download/<filename>')
def download_file(filename):
    try:
        file_path = os.path.join(app.root_path, filename)
        
        # Verificar que el archivo existe
        if not os.path.exists(file_path):
            print(f"Archivo no encontrado: {file_path}")
            abort(404)
        
        # Enviar el archivo
        return send_file(
            file_path,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        print(f"Error al descargar archivo: {str(e)}")
        abort(500)

@app.route('/history')
def history():
    try:
        # Obtener historial de Firebase
        history_records = firebase.get_history()
        
        # Calcular estadísticas
        total_searches = len(history_records)
        total_files = sum(len(record.get('files', [])) for record in history_records)
        total_findings = sum(
            len(finding['findings']) 
            for record in history_records 
            for finding in record.get('files', [])
        )
        
        stats = {
            'total_searches': total_searches,
            'total_files': total_files,
            'total_findings': total_findings
        }
        
        return render_template('history.html', 
                             history=history_records,
                             stats=stats)
    except Exception as e:
        print(f"Error obteniendo historial: {str(e)}")
        return render_template('history.html', 
                             history=[],
                             stats={'total_searches': 0, 
                                   'total_files': 0,
                                   'total_findings': 0},
                             error="Error al cargar el historial")

@app.route('/preview/<path:filename>')
def preview_file(filename):
    """Previsualiza un archivo de resultados."""
    try:
        print(f"Intentando previsualizar archivo: {filename}")
        results_path = os.path.join(filename)
        if os.path.exists(results_path):
            return send_file(results_path, as_attachment=False)
        
        print(f"Archivo no encontrado para previsualización: {filename}")
        print(f"Ruta buscada: {results_path}")
        abort(404)
        
    except Exception as e:
        print(f"Error al previsualizar archivo: {str(e)}")
        abort(404)

@app.route('/dashboard')
def dashboard():
    try:
        dashboard_data = firebase.get_dashboard_data()
        stats = dashboard_data.get('general_stats', {})
        
        # Valores por defecto para file_types
        default_file_types = {
            'pdf': 0,
            'docx': 0,
            'xlsx': 0,
            'pptx': 0,
            'txt': 0,
            'others': 0
        }
        
        try:
            file_types = firebase.get_file_type_stats()
            if not file_types:
                file_types = default_file_types
        except Exception as e:
            print(f"Error obteniendo estadísticas de tipos de archivo: {str(e)}")
            file_types = default_file_types
        
        # Preparar datos para los gráficos
        top_terms_data = {
            'labels': [term['term'] for term in dashboard_data['top_terms']],
            'counts': [term['search_count'] for term in dashboard_data['top_terms']]
        }
        
        weekly_data = {
            'searches': [0] * 7  # Inicializar con ceros para cada día
        }
        for stat in dashboard_data['weekly_stats']:
            weekly_data['searches'][int(stat['day_of_week'])] = stat['searches']
        
        # Obtener estadísticas de archivos no analizados
        try:
            unprocessed_stats = firebase.get_unprocessed_files_stats() or {
                'dates': [],
                'counts': []
            }
        except Exception as e:
            print(f"Error obteniendo estadísticas de archivos no analizados: {str(e)}")
            unprocessed_stats = {
                'dates': [],
                'counts': []
            }
        
        return render_template('dashboard.html',
                             stats=stats,
                             recent_searches=dashboard_data['recent_searches'],
                             top_terms_data=top_terms_data,
                             weekly_data=weekly_data,
                             file_types=file_types,
                             unprocessed_stats=unprocessed_stats)
    
    except Exception as e:
        print(f"Error en dashboard: {str(e)}")
        # Proporcionar datos por defecto en caso de error
        default_stats = {
            'total_searches': 0,
            'total_findings': 0,
            'total_files': 0,
            'avg_execution_time': 0,
            'daily_increase': 0,
            'active_users': 0
        }
        default_data = {
            'labels': [],
            'counts': []
        }
        default_file_types = {
            'pdf': 0,
            'docx': 0,
            'xlsx': 0,
            'pptx': 0,
            'txt': 0,
            'others': 0
        }
        return render_template('dashboard.html',
                             stats=default_stats,
                             recent_searches=[],
                             top_terms_data=default_data,
                             weekly_data={'searches': [0] * 7},
                             file_types=default_file_types,
                             unprocessed_stats={'dates': [], 'counts': []})

@app.route('/browse_directory')
def browse_directory():
    try:
        root = Tk()
        root.withdraw()  # Ocultar la ventana principal
        root.attributes('-topmost', True)  # Mantener el diálogo encima
        
        directory = filedialog.askdirectory()
        root.destroy()
        
        if directory:
            return jsonify({
                'success': True,
                'path': directory
            })
        else:
            return jsonify({
                'success': False,
                'error': 'No se seleccionó ningún directorio'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/system_metrics')
def system_metrics():
    try:
        # Variables para almacenar los bytes anteriores
        if not hasattr(app, 'previous_bytes'):
            app.previous_bytes = {
                'sent': 0,
                'recv': 0,
                'timestamp': time.time()
            }

        # Obtener métricas del sistema con manejo de errores mejorado
        try:
            cpu_percent = round(float(psutil.cpu_percent(interval=0.1)), 2)
        except:
            cpu_percent = 0.0

        try:
            memory = psutil.virtual_memory()
            memory_percent = round(float(memory.percent), 2)
        except:
            memory_percent = 0.0

        try:
            disk = psutil.disk_usage('/')
            disk_percent = round(float(disk.percent), 2)
        except:
            disk_percent = 0.0

        try:
            # Obtener estadísticas de red
            net_io = psutil.net_io_counters()
            current_time = time.time()
            time_delta = current_time - app.previous_bytes['timestamp']
            
            # Calcular la tasa de transferencia en MB/s
            bytes_sent_sec = (net_io.bytes_sent - app.previous_bytes['sent']) / time_delta
            bytes_recv_sec = (net_io.bytes_recv - app.previous_bytes['recv']) / time_delta
            
            # Actualizar valores previos
            app.previous_bytes = {
                'sent': net_io.bytes_sent,
                'recv': net_io.bytes_recv,
                'timestamp': current_time
            }
            
            # Convertir a MB/s y calcular el uso total
            network_usage = round((bytes_sent_sec + bytes_recv_sec) / (1024 * 1024), 2)
            
            network_stats = {
                'bytes_sent': net_io.bytes_sent,
                'bytes_recv': net_io.bytes_recv,
                'packets_sent': net_io.packets_sent,
                'packets_recv': net_io.packets_recv,
                'usage_percent': network_usage  # MB/s
            }
        except:
            network_stats = {
                'bytes_sent': 0,
                'bytes_recv': 0,
                'packets_sent': 0,
                'packets_recv': 0,
                'usage_percent': 0
            }

        # Obtener estadísticas de tipos de archivo
        try:
            file_types = firebase.get_file_type_stats()
        except:
            file_types = {
                'pdf': 0, 'docx': 0, 'xlsx': 0,
                'pptx': 0, 'txt': 0, 'others': 0
            }
        
        return jsonify({
            'cpu': cpu_percent,
            'memory': memory_percent,
            'disk': disk_percent,
            'network': network_stats,
            'file_types': {
                'pdf': file_types.get('pdf', 0),
                'word': file_types.get('docx', 0),
                'excel': file_types.get('xlsx', 0),
                'powerpoint': file_types.get('pptx', 0),
                'text': file_types.get('txt', 0),
                'others': file_types.get('others', 0)
            }
        })
    except Exception as e:
        print(f"Error obteniendo métricas del sistema: {str(e)}")
        return jsonify({
            'cpu': 0.0,
            'memory': 0.0,
            'disk': 0.0,
            'network': {
                'bytes_sent': 0,
                'bytes_recv': 0,
                'packets_sent': 0,
                'packets_recv': 0,
                'usage_percent': 0
            },
            'file_types': {
                'pdf': 0,
                'word': 0,
                'excel': 0,
                'powerpoint': 0,
                'text': 0,
                'others': 0
            }
        })

@app.route('/system_metrics_history')
def system_metrics_history():
    try:
        metrics = firebase.get_system_metrics_history()
        return jsonify(metrics)
    except Exception as e:
        print(f"Error obteniendo historial de métricas: {str(e)}")
        return jsonify([])

@app.route('/cancel_search', methods=['POST'])
def cancel_search():
    try:
        data = request.json
        search_id = data.get('search_id')
        
        if not search_id:
            return jsonify({'error': 'ID de búsqueda no proporcionado'}), 400
        
        # Emitir evento de cancelación
        socketio.emit('search_cancelled', {
            'search_id': search_id,
            'message': 'Búsqueda cancelada por el usuario'
        })
        
        return jsonify({'success': True, 'message': 'Búsqueda cancelada'})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@socketio.on('start_search')
def process_search(data):
    try:
        print("Datos recibidos:", data)
        
        if not isinstance(data, dict):
            raise ValueError('Datos de búsqueda inválidos')
            
        directory = data.get('directory')
        keywords = data.get('keywords', [])
        
        print(f"Iniciando búsqueda en directorio: {directory}")
        print(f"Palabras clave a buscar: {keywords}")
        
        # Validar datos
        if not directory or not keywords:
            print(f"Datos inválidos - directory: {directory}, keywords: {keywords}")
            raise ValueError('Faltan parámetros requeridos')
            
        # Validar que el directorio existe
        if not os.path.exists(directory):
            raise ValueError(f'El directorio no existe: {directory}')
            
        # Validar keywords
        if not isinstance(keywords, list) or not all(isinstance(k, str) for k in keywords):
            raise ValueError('Keywords inválidas')
            
        start_time = time.time()
        processor = DocumentProcessor()
        
        # Contar archivos totales antes de procesar
        total_files = sum(1 for _ in processor.get_processable_files(Path(directory)))
        
        # Datos de la búsqueda para Firebase
        search_data = {
            'directory': directory,
            'keywords': keywords,
            'total_files': total_files,
            'start_time': start_time
        }
        
        # Procesar la búsqueda y almacenar resultados
        all_results = []
        unprocessed_files = []
        
        print("Iniciando procesamiento de archivos...")
        
        # Procesar el generador y acumular resultados
        for result in processor.process_directory(Path(directory), keywords, progress_callback):
            print(f"Resultado obtenido: {result}")
            if isinstance(result, dict):
                if 'error' in result:
                    print(f"Archivo no procesado: {result}")
                    unprocessed_files.append({
                        'name': result.get('file_name', ''),
                        'reason': result.get('error', 'Error desconocido')
                    })
                else:
                    print(f"Resultado válido encontrado: {result}")
                    all_results.append(result)
        
        print(f"Total de resultados encontrados: {len(all_results)}")
        print(f"Total de archivos no procesados: {len(unprocessed_files)}")
        
        # Guardar resultados en Firebase
        try:
            search_id = firebase.save_search_results(search_data, all_results)
            if not search_id:
                raise Exception("Error al guardar resultados en Firebase")
        except Exception as e:
            print(f"Error guardando en Firebase: {str(e)}")
            raise
        
        if not all_results:
            print("No se encontraron resultados para escribir en el archivo")
            raise Exception("No se encontraron coincidencias en la búsqueda")
        
        # Actualizar tiempo de ejecución
        execution_time = round(time.time() - start_time, 2)
        
        socketio.emit('search_complete', {
            'status': 'success',
            'total_results': len(all_results),
            'unprocessed_files': unprocessed_files,
            'search_id': search_id
        })
        
    except Exception as e:
        print(f"Error en process_search: {str(e)}")
        socketio.emit('search_error', {
            'error': str(e)
        })

@app.route('/api/search_results/<search_id>')
def get_search_results(search_id):
    try:
        results = firebase.get_search_results(search_id)
        return jsonify(results)
    except Exception as e:
        print(f"Error obteniendo resultados de búsqueda: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/check_file/<path:filename>')
def check_file(filename):
    """Verifica si un archivo existe y es accesible."""
    try:
        file_path = os.path.join(app.root_path, filename)
        if os.path.exists(file_path) and os.access(file_path, os.R_OK):
            return jsonify({'exists': True}), 200
        return jsonify({'exists': False, 'error': 'Archivo no encontrado'}), 404
    except Exception as e:
        return jsonify({'exists': False, 'error': str(e)}), 500

@app.route('/preview')
def preview():
    """Recibe la ruta completa del archivo desde el frontend y lo sirve"""
    file_path = request.args.get('file')

    if not file_path or not os.path.exists(file_path):
        return "Archivo no encontrado", 404

    return send_file(file_path)
BASE_DIRECTORY = 'G:'
@app.route('/get-excel')
def get_excel():
    # Obtener la ruta del archivo desde la URL (parámetro 'file')
    file_path = request.args.get('file')

    if not file_path:
        return jsonify({"error": "Debe proporcionar una ruta de archivo"}), 400

    # Validar si el archivo existe y tiene extensión .xlsx
    full_path = os.path.join(BASE_DIRECTORY, file_path)
    
    if not os.path.isfile(full_path) or not file_path.endswith('.xlsx'):
        return jsonify({"error": "Archivo no encontrado"}), 404

    # Si el archivo existe, se sirve al cliente
    return send_file(full_path, as_attachment=True)


if __name__ == '__main__':
    # Crear directorios necesarios
    for directory in ['resultados']:
        os.makedirs(directory, exist_ok=True)
        # En sistemas Unix, establecer permisos
        if os.name != 'nt':
            os.chmod(directory, 0o777)  # Dar permisos completos
    
    # Obtener el puerto de la variable de entorno (Render lo define automáticamente)
    port = int(os.getenv("PORT", 5000))  # Usa 5000 por defecto si no se encuentra la variable
    
    socketio.run(app, host="0.0.0.0", port=port, debug=True)
