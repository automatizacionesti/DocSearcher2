import os
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
from typing import Dict, List
import time

class FirebaseManager:
    def __init__(self):
        # Inicializar Firebase (asumiendo que tienes el archivo de credenciales)
        # Usar ruta absoluta para el archivo de credenciales
        cred_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'firebase-credentials.json')
        if not os.path.exists(cred_path):
            raise FileNotFoundError(f"No se encontró el archivo de credenciales en: {cred_path}")
        
        cred = credentials.Certificate(cred_path)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        self.db = firestore.client()

    def save_search_results(self, search_data: Dict, results: List[Dict]):
        """
        Guarda los resultados de búsqueda en Firebase.
        
        Args:
            search_data: Datos de la búsqueda (directorio, keywords, etc)
            results: Lista de resultados encontrados
        """
        try:
            # Crear referencia a la colección de búsquedas
            search_ref = self.db.collection('searches').document()
            
            # Datos básicos de la búsqueda
            search_info = {
                'directory': search_data['directory'],
                'keywords': search_data['keywords'],
                'timestamp': datetime.now(),
                'total_files_processed': search_data.get('total_files', 0),
                'total_results': len(results),
                'status': 'completed',
                'execution_time': time.time() - search_data.get('start_time', time.time())
            }
            
            # Guardar información de la búsqueda
            search_ref.set(search_info)
            
            # Procesar cada resultado
            for result in results:
                if 'findings' in result:
                    file_path = result.get('path', '') or result.get('file_name', '')
                    
                    # Referencia al documento del archivo
                    file_ref = self.db.collection('files').document(self._get_file_id(file_path))
                    
                    # Preparar datos del archivo
                    file_data = {
                        'file_name': os.path.basename(file_path),
                        'file_path': file_path,
                        'file_type': result.get('file_type', ''),
                        'findings': result.get('findings', []),
                        'keywords': search_data['keywords'],
                        'last_updated': datetime.now()
                    }
                    
                    # Obtener o crear documento del archivo
                    file_doc = file_ref.get()
                    if file_doc.exists:
                        # Actualizar archivo existente
                        existing_data = file_doc.to_dict()
                        existing_data['findings'] = self._merge_findings(
                            existing_data.get('findings', []),
                            file_data['findings']
                        )
                        existing_data['keywords'] = list(set(
                            existing_data.get('keywords', []) + file_data['keywords']
                        ))
                        existing_data['last_updated'] = file_data['last_updated']
                        file_ref.update(existing_data)
                    else:
                        # Crear nuevo documento de archivo
                        file_ref.set(file_data)
            
            return search_ref.id
            
        except Exception as e:
            print(f"Error guardando en Firebase: {str(e)}")
            raise

    def _get_file_id(self, file_path: str) -> str:
        """Genera un ID único para el archivo basado en su ruta."""
        return file_path.replace('/', '_').replace('\\', '_')

    def _update_existing_file(self, file_ref, result: Dict, keywords: List[str]):
        """Actualiza un archivo existente con nuevos hallazgos."""
        try:
            # Obtener datos actuales
            current_data = file_ref.get().to_dict()
            
            # Actualizar keywords (sin duplicados)
            current_keywords = set(current_data.get('keywords', []))
            current_keywords.update(keywords)
            
            # Actualizar hallazgos
            current_findings = current_data.get('findings', [])
            new_findings = result.get('findings', [])
            
            # Combinar hallazgos evitando duplicados
            combined_findings = self._merge_findings(current_findings, new_findings)
            
            # Actualizar documento
            file_ref.update({
                'keywords': list(current_keywords),
                'findings': combined_findings,
                'last_updated': datetime.now()
            })
            
        except Exception as e:
            print(f"Error actualizando archivo: {str(e)}")
            raise

    def _create_new_file(self, file_ref, result: Dict, keywords: List[str]):
        """Crea un nuevo documento para un archivo."""
        try:
            file_data = {
                'file_name': result.get('file_name', ''),
                'file_type': result.get('file_type', ''),
                'keywords': keywords,
                'findings': result.get('findings', []),
                'created_at': datetime.now(),
                'last_updated': datetime.now()
            }
            file_ref.set(file_data)
            
        except Exception as e:
            print(f"Error creando nuevo archivo: {str(e)}")
            raise

    def _merge_findings(self, current_findings: List[Dict], new_findings: List[Dict]) -> List[Dict]:
        """Combina hallazgos existentes con nuevos, evitando duplicados."""
        # Usar un set para tracking de hallazgos únicos
        unique_findings = {}
        
        # Procesar hallazgos existentes
        for finding in current_findings:
            key = f"{finding['palabra']}_{finding['contexto']}"
            unique_findings[key] = finding
        
        # Agregar nuevos hallazgos
        for finding in new_findings:
            key = f"{finding['palabra']}_{finding['contexto']}"
            if key not in unique_findings:
                unique_findings[key] = finding
        
        return list(unique_findings.values())

    def get_recent_searches(self, limit: int = 10):
        """Obtiene las búsquedas más recientes."""
        try:
            searches = self.db.collection('searches')\
                .order_by('timestamp', direction=firestore.Query.DESCENDING)\
                .limit(limit)\
                .stream()
            
            return [doc.to_dict() for doc in searches]
            
        except Exception as e:
            print(f"Error obteniendo búsquedas recientes: {str(e)}")
            return []

    def get_file_details(self, file_path: str):
        """Obtiene los detalles de un archivo específico."""
        try:
            file_id = self._get_file_id(file_path)
            doc = self.db.collection('files').document(file_id).get()
            return doc.to_dict() if doc.exists else None
            
        except Exception as e:
            print(f"Error obteniendo detalles del archivo: {str(e)}")
            return None

    def get_search_results(self, search_id: str) -> List[Dict]:
        """
        Obtiene los resultados de una búsqueda específica.
        
        Args:
            search_id: ID de la búsqueda
            
        Returns:
            List[Dict]: Lista de resultados formateados
        """
        try:
            # Obtener la búsqueda
            search_doc = self.db.collection('searches').document(search_id).get()
            if not search_doc.exists:
                raise ValueError(f"No se encontró la búsqueda con ID: {search_id}")
            
            search_data = search_doc.to_dict()
            
            # Obtener todos los archivos relacionados con esta búsqueda
            files_query = self.db.collection('files')\
                .where('keywords', 'array_contains_any', search_data.get('keywords', []))\
                .stream()
            
            # Formatear resultados
            results = []
            for file_doc in files_query:
                file_data = file_doc.to_dict()
                results.append({
                    'file_name': file_data.get('file_name', ''),
                    'file_type': file_data.get('file_type', ''),
                    'findings': [
                        {
                            'palabra': finding.get('palabra', ''),
                            'contexto': finding.get('contexto', ''),
                            'path': json.loads(f'"{finding.get("path", "")}"')
                        }
                        for finding in file_data.get('findings', [])
                        if any(kw.lower() in finding.get('palabra', '').lower() 
                              for kw in search_data.get('keywords', []))
                    ]
                })
            
            return results
            
        except Exception as e:
            print(f"Error obteniendo resultados de búsqueda: {str(e)}")
            raise 

    def get_history(self):
        """Obtiene el historial de búsquedas detallado desde Firebase."""
        try:
            # Obtener la colección de búsquedas y archivos
            searches_ref = self.db.collection('searches')
            files_ref = self.db.collection('files')
            
            # Obtener búsquedas recientes
            search_docs = searches_ref.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(10).get()
            
            history = []
            for search_doc in search_docs:
                search_data = search_doc.to_dict()
                timestamp = search_data.get('timestamp')
                search_keywords = search_data.get('keywords', [])
                
                # Obtener archivos relacionados con esta búsqueda
                files_query = files_ref.where('keywords', 'array_contains_any', search_keywords).stream()
                
                file_results = []
                for file_doc in files_query:
                    file_data = file_doc.to_dict()
                    
                    # Filtrar hallazgos relacionados con las palabras clave de esta búsqueda
                    relevant_findings = [
                        finding for finding in file_data.get('findings', [])
                        if any(kw.lower() in finding.get('palabra', '').lower() 
                              for kw in search_keywords)
                    ]
                    
                    if relevant_findings:
                        file_results.append({
                            'file_name': file_data.get('file_name', ''),
                            'file_path': file_data.get('file_path', ''),
                            'file_type': file_data.get('file_type', ''),
                            'findings': relevant_findings
                        })
                
                # Formatear la fecha
                if isinstance(timestamp, datetime):
                    formatted_date = timestamp.strftime('%d/%m/%Y %H:%M')
                else:
                    formatted_date = datetime.now().strftime('%d/%m/%Y %H:%M')
                
                # Formatear los datos para la vista
                search_record = {
                    'id': search_doc.id,
                    'keywords': search_keywords,
                    'directory': search_data.get('directory', ''),
                    'total_results': search_data.get('total_results', 0),
                    'total_files': search_data.get('total_files_processed', 0),
                    'status': search_data.get('status', 'completed'),
                    'date': formatted_date,
                    'files': file_results,
                    'execution_time': search_data.get('execution_time', 0),
                    'has_results': bool(search_data.get('total_results', 0) > 0)
                }
                
                history.append(search_record)
            
            return history
            
        except Exception as e:
            print(f"Error obteniendo historial: {str(e)}")
            return [] 