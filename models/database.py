from datetime import datetime
import sqlite3
import os
import json

class Database:
    def __init__(self):
        self.db_path = 'static/database/search_history.db'
        os.makedirs('static/database', exist_ok=True)
        self.init_db()

    def get_connection(self):
        """
        Obtiene una conexión a la base de datos.
        
        Returns:
            sqlite3.Connection: Conexión a la base de datos
        """
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            return conn
        except Exception as e:
            print(f"Error al obtener conexión a la base de datos: {str(e)}")
            raise

    def init_db(self):
        """Inicializa la base de datos y crea las tablas necesarias."""
        try:
            conn = self.get_connection()
            
            # Crear tabla principal de búsquedas
            with conn:
                cursor = conn.cursor()
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS searches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    keywords TEXT NOT NULL,
                    directory TEXT NOT NULL,
                    results_file TEXT NOT NULL,
                    total_results INTEGER DEFAULT 0,
                    total_files INTEGER DEFAULT 0,
                    execution_time REAL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Crear índice para búsqueda rápida por nombre de archivo
                cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_results_file 
                ON searches(results_file)
            """)
            
                conn.commit()
            
        except Exception as e:
            print(f"Error inicializando la base de datos: {str(e)}")

    def add_search(self, keywords, directory, results_file, total_results, execution_time, total_files):
        """
        Agrega un nuevo registro de búsqueda a la base de datos.
        
        Args:
            keywords (list): Lista de palabras clave usadas en la búsqueda
            directory (str): Directorio donde se realizó la búsqueda
            results_file (str): Nombre del archivo de resultados
            total_results (int): Número total de resultados encontrados
            execution_time (float): Tiempo de ejecución en segundos
            total_files (int): Número total de archivos procesados
        
        Returns:
            int: ID del registro creado
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO searches (
                        keywords, directory, results_file, 
                        total_results, execution_time, total_files,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                """, (
                    ','.join(keywords), directory, results_file,
                    total_results, execution_time, total_files
                ))
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            print(f"Error al agregar búsqueda: {str(e)}")
            raise

    def get_dashboard_data(self):
        """Obtiene los datos para el dashboard con manejo de errores mejorado."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            try:
                # Verificar si las tablas existen
                cursor.execute('''
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND (name='search_history' OR name='search_terms')
                ''')
                existing_tables = [row['name'] for row in cursor.fetchall()]
                
                if 'search_history' not in existing_tables or 'search_terms' not in existing_tables:
                    raise Exception("Las tablas necesarias no existen")

                # Términos más buscados (con manejo de NULL)
                top_terms = cursor.execute('''
                    SELECT 
                        term,
                        COUNT(*) as search_count,
                        COALESCE(SUM(occurrences), 0) as total_occurrences
                    FROM search_terms
                    GROUP BY term
                    ORDER BY search_count DESC
                    LIMIT 10
                ''').fetchall()

                # Estadísticas por día de la semana
                weekly_stats = cursor.execute('''
                    SELECT 
                        COALESCE(strftime('%w', search_date), '0') as day_of_week,
                        COUNT(*) as searches,
                        COALESCE(AVG(total_results), 0) as avg_results
                    FROM search_history
                    GROUP BY day_of_week
                    ORDER BY day_of_week
                ''').fetchall()

                # Estadísticas generales
                general_stats = cursor.execute('''
                    SELECT 
                        COUNT(*) as total_searches,
                        COALESCE(SUM(total_results), 0) as total_findings,
                        COALESCE(SUM(total_files_analyzed), 0) as total_files,
                        COALESCE(AVG(execution_time), 0) as avg_execution_time,
                        (
                            SELECT COUNT(*) 
                            FROM search_history 
                            WHERE date(search_date) = date('now')
                        ) as daily_searches
                    FROM search_history
                ''').fetchone()

                # Convertir a diccionario y agregar campos calculados
                stats_dict = dict(general_stats) if general_stats else {
                    'total_searches': 0,
                    'total_findings': 0,
                    'total_files': 0,
                    'avg_execution_time': 0,
                    'daily_searches': 0
                }

                # Calcular incremento diario
                yesterday_searches = cursor.execute('''
                    SELECT COUNT(*) as count
                    FROM search_history
                    WHERE date(search_date) = date('now', '-1 day')
                ''').fetchone()['count']

                today_searches = stats_dict['daily_searches']
                
                if yesterday_searches > 0:
                    daily_increase = ((today_searches - yesterday_searches) / yesterday_searches) * 100
                else:
                    daily_increase = 100 if today_searches > 0 else 0

                stats_dict['daily_increase'] = round(daily_increase, 1)

                # Usuarios activos (última hora)
                active_users = cursor.execute('''
                    SELECT COUNT(DISTINCT strftime('%H:%M', search_date)) as count
                    FROM search_history
                    WHERE datetime(search_date) >= datetime('now', '-1 hour')
                ''').fetchone()['count']

                stats_dict['active_users'] = active_users

                # Búsquedas recientes
                recent_searches = cursor.execute('''
                    SELECT 
                        search_date,
                        keywords,
                        total_results,
                        total_files_analyzed,
                        COALESCE(execution_time, 0) as execution_time
                    FROM search_history
                    ORDER BY search_date DESC
                    LIMIT 5
                ''').fetchall()

                # Formatear fechas y keywords para las búsquedas recientes
                formatted_searches = []
                for search in recent_searches:
                    search_dict = dict(search)
                    try:
                        search_dict['keywords'] = ', '.join(json.loads(search_dict['keywords']))
                    except:
                        search_dict['keywords'] = str(search_dict['keywords'])
                    
                    try:
                        date_obj = datetime.strptime(search_dict['search_date'], '%Y-%m-%d %H:%M:%S.%f')
                        search_dict['search_date'] = date_obj.strftime('%d/%m/%Y %H:%M:%S')
                    except:
                        pass
                    
                    formatted_searches.append(search_dict)

                return {
                    'top_terms': top_terms,
                    'weekly_stats': weekly_stats,
                    'general_stats': stats_dict,
                    'recent_searches': formatted_searches
                }

            except Exception as e:
                print(f"Error obteniendo datos del dashboard: {str(e)}")
                return {
                    'top_terms': [],
                    'weekly_stats': [],
                    'general_stats': {
                        'total_searches': 0,
                        'total_findings': 0,
                        'total_files': 0,
                        'avg_execution_time': 0,
                        'daily_searches': 0,
                        'daily_increase': 0,
                        'active_users': 0
                    },
                    'recent_searches': []
                }

    def get_history(self):
        """Obtiene el historial de búsquedas."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT 
                        h.id,
                        h.created_at as search_date,
                        h.keywords,
                        h.directory,
                        h.results_file,
                        h.total_results,
                        h.total_files,
                        h.execution_time
                    FROM searches h
                    ORDER BY h.created_at DESC
                ''')
                history = cursor.fetchall()

            # Formatear resultados
            formatted_history = []
            for record in history:
                record_dict = dict(record)
                
                # Verificar si el archivo existe
                results_file = record_dict.get('results_file')
                if results_file:
                    results_path = os.path.join('static/results', results_file)
                    
                    if os.path.exists(results_path):
                        try:
                            # Formatear keywords
                            keywords = json.loads(record_dict['keywords'])
                            record_dict['keywords'] = ', '.join(keywords) if isinstance(keywords, list) else str(keywords)
                            
                            # Formatear fecha
                            date_obj = datetime.strptime(str(record_dict['search_date']), '%Y-%m-%d %H:%M:%S')
                            record_dict['search_date'] = date_obj.strftime('%d/%m/%Y %H:%M:%S')
                            
                            formatted_history.append(record_dict)
                        except Exception as e:
                            print(f"Error formateando registro {record_dict.get('id')}: {str(e)}")
                            continue

            return formatted_history
            
        except Exception as e:
            print(f"Error obteniendo historial: {str(e)}")
            return []

    def store_system_metrics(self, cpu_usage, memory_usage, disk_usage, timestamp=None):
        """Almacena las métricas del sistema en la base de datos."""
        if timestamp is None:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            try:
                # Crear tabla si no existe
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS system_metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp DATETIME NOT NULL,
                        cpu_usage REAL NOT NULL,
                        memory_usage REAL NOT NULL,
                        disk_usage REAL NOT NULL
                    )
                ''')
                
                # Insertar métricas
                cursor.execute('''
                    INSERT INTO system_metrics 
                    (timestamp, cpu_usage, memory_usage, disk_usage)
                    VALUES (?, ?, ?, ?)
                ''', (
                    timestamp,
                    float(cpu_usage),
                    float(memory_usage),
                    float(disk_usage)
                ))
                
                # Mantener solo los últimos 1000 registros
                cursor.execute('''
                    DELETE FROM system_metrics 
                    WHERE id NOT IN (
                        SELECT id FROM system_metrics 
                        ORDER BY timestamp DESC 
                        LIMIT 1000
                    )
                ''')
                
                conn.commit()
            except Exception as e:
                print(f"Error almacenando métricas del sistema: {str(e)}")
                conn.rollback() 

    def get_system_metrics_history(self, limit=10):
        """Obtiene el historial de métricas del sistema."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    SELECT timestamp, cpu_usage, memory_usage, disk_usage
                    FROM system_metrics
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (limit,))
                
                metrics = cursor.fetchall()
                return [{
                    'timestamp': metric[0],
                    'cpu': metric[1],
                    'memory': metric[2],
                    'disk': metric[3]
                } for metric in metrics]
                
            except Exception as e:
                print(f"Error obteniendo historial de métricas: {str(e)}")
                return [] 

    def get_file_type_stats(self):
        """Obtiene estadísticas de tipos de archivo."""
        try:
            query = """
                SELECT file_type, COUNT(*) as count
                FROM file_type_stats
                GROUP BY file_type
            """
            with self.get_connection() as conn:
                cursor = conn.cursor()
                result = cursor.execute(query).fetchall()
            return {row['file_type']: row['count'] for row in result}
        except Exception as e:
            print(f"Error obteniendo estadísticas de tipos de archivo: {str(e)}")
            return None

    def get_unprocessed_files_stats(self):
        """Obtiene estadísticas de archivos no procesados por día."""
        try:
            query = """
                SELECT 
                    DATE(created_at) as date,
                    COUNT(*) as count
                FROM unprocessed_files
                GROUP BY DATE(created_at)
                ORDER BY date DESC
                LIMIT 30
            """
            with self.get_connection() as conn:
                cursor = conn.cursor()
                result = cursor.execute(query).fetchall()
            
            # Formatear fechas y preparar datos
            dates = []
            counts = []
            for row in result:
                dates.append(row['date'].strftime('%Y-%m-%d'))
                counts.append(row['count'])
            
            return {
                'dates': dates,
                'counts': counts
            }
        except Exception as e:
            print(f"Error obteniendo estadísticas de archivos no procesados: {str(e)}")
            return None

    def add_unprocessed_file(self, file_name, error_message, search_id=None):
        """Registra un archivo no procesado en la base de datos."""
        try:
            query = """
                INSERT INTO unprocessed_files (file_name, error_message, search_id, created_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (file_name, error_message, search_id))
                conn.commit()
        except Exception as e:
            print(f"Error registrando archivo no procesado: {str(e)}")
            raise

    def add_file_type_stat(self, search_id, file_type, count):
        """Agrega estadísticas de tipo de archivo para una búsqueda."""
        try:
            query = """
                INSERT INTO file_type_stats (search_id, file_type, count)
                VALUES (?, ?, ?)
            """
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (search_id, file_type, count))
                conn.commit()
        except Exception as e:
            print(f"Error agregando estadística de tipo de archivo: {str(e)}")
            raise

    def execute_query(self, query, params=()):
        """Ejecuta una consulta SQL con parámetros opcionales."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                return cursor.fetchall()
        except Exception as e:
            print(f"Error ejecutando consulta: {str(e)}")
            raise

    def update_search(self, search_id, results_file=None, total_results=None, execution_time=None):
        """Actualiza un registro de búsqueda existente."""
        try:
            update_fields = []
            params = []
            
            if results_file is not None:
                update_fields.append("results_file = ?")
                params.append(results_file)
            
            if total_results is not None:
                update_fields.append("total_results = ?")
                params.append(total_results)
            
            if execution_time is not None:
                update_fields.append("execution_time = ?")
                params.append(execution_time)
            
            if update_fields:
                query = f"""
                    UPDATE searches 
                    SET {', '.join(update_fields)}
                    WHERE id = ?
                """
                params.append(search_id)
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query, params)
                    conn.commit()
                
        except Exception as e:
            print(f"Error actualizando búsqueda: {str(e)}")
            raise

    def get_search_by_filename(self, filename):
        """Obtiene la información de búsqueda por nombre de archivo."""
        try:
            query = """
                SELECT *
                FROM searches
                WHERE results_file = ?
            """
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (filename,))
                results = cursor.fetchall()
            return dict(results[0]) if results else None
        except Exception as e:
            print(f"Error buscando archivo: {str(e)}")
            return None 

    def _check_and_migrate_data(self):
        """Verifica y migra datos de la tabla antigua a la nueva si es necesario."""
        try:
            # Verificar si existe la tabla antigua
            old_table = self.execute_query("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='search_history'
            """)
            
            if old_table:
                # Migrar datos
                self.execute_query("""
                    INSERT INTO searches (
                        keywords, directory, results_file, 
                        total_results, total_files, execution_time, created_at
                    )
                    SELECT 
                        keywords, directory, results_file,
                        total_results, total_files_analyzed, execution_time, search_date
                    FROM search_history
                    WHERE results_file NOT IN (SELECT results_file FROM searches)
                """)
                self.conn.commit()
                
                # Opcional: Eliminar tabla antigua después de migrar
                # self.execute_query("DROP TABLE search_history")
                # self.conn.commit()
            
        except Exception as e:
            print(f"Error durante la migración: {str(e)}") 