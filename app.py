import streamlit as st
import numpy as np
import pandas as pd
import folium
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

# Configuración de diseño de la página de Streamlit
st.set_page_config(
    page_title="Optimizador de Ruteo CVRP - Sabor Sabanero",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos personalizados con CSS para mejorar la UI
st.markdown("""
<style>
    .main-title {
        font-size: 38px;
        font-weight: bold;
        color: #1E3A8A;
        margin-bottom: 5px;
    }
    .sub-title {
        font-size: 16px;
        color: #4B5563;
        margin-bottom: 25px;
    }
    .metric-card {
        background-color: #F3F4F6;
        padding: 15px;
        border-radius: 8px;
        border-left: 5px solid #2563EB;
    }
</style>
""", unsafe_allow_html=True)

# Inicializar estados de la sesión para mantener los datos de forma interactiva
if 'depot_name' not in st.session_state:
    st.session_state.depot_name = "CEDI Tocancipá"
if 'depot_lat' not in st.session_state:
    st.session_state.depot_lat = 4.964
if 'depot_lon' not in st.session_state:
    st.session_state.depot_lon = -73.912

# Datos iniciales para el botón de "Cargar Caso de Estudio"
default_clients = pd.DataFrame([
    {"Nombre": "Chía", "Latitud (Y)": 4.863, "Longitud (X)": -74.053, "Demanda (kg)": 1100},
    {"Nombre": "Cajicá", "Latitud (Y)": 4.918, "Longitud (X)": -74.029, "Demanda (kg)": 750},
    {"Nombre": "Zipaquirá", "Latitud (Y)": 4.996, "Longitud (X)": -74.003, "Demanda (kg)": 1400},
    {"Nombre": "Sopó", "Latitud (Y)": 4.908, "Longitud (X)": -73.938, "Demanda (kg)": 900},
    {"Nombre": "Briceño", "Latitud (Y)": 4.945, "Longitud (X)": -73.921, "Demanda (kg)": 500}
])

if 'clients_df' not in st.session_state:
    st.session_state.clients_df = default_clients.copy()

# ----------------- BARRA LATERAL (SIDEBAR) -----------------
st.sidebar.header("⚙️ Configuración de la Flota")
num_vehicles = st.sidebar.number_input("Número de camiones disponibles", min_value=1, max_value=10, value=3, step=1)
vehicle_capacity = st.sidebar.number_input("Capacidad máxima por camión (kg)", min_value=500, max_value=10000, value=2200, step=100)
sf_factor = st.sidebar.number_input("Factor métrico de escala (SF m/grado)", min_value=100000, max_value=120000, value=111000, step=500)

st.sidebar.markdown("---")
st.sidebar.markdown("### 🏬 Ubicación del Depósito (CEDI)")
depot_name = st.sidebar.text_input("Nombre del CEDI", value=st.session_state.depot_name)
depot_lat = st.sidebar.number_input("Latitud CEDI (Y)", value=st.session_state.depot_lat, format="%.6f")
depot_lon = st.sidebar.number_input("Longitud CEDI (X)", value=st.session_state.depot_lon, format="%.6f")

# Guardar cambios del CEDI en el estado de la sesión
st.session_state.depot_name = depot_name
st.session_state.depot_lat = depot_lat
st.session_state.depot_lon = depot_lon

# ----------------- PANEL PRINCIPAL -----------------
st.markdown('<p class="main-title">🚚 Optimizador de Ruteo de Vehículos (CVRP)</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">Diseña y simula rutas de distribución eficientes de última milla controlando demandas y capacidades de flota en mapas interactivos de Colombia.</p>', unsafe_allow_html=True)

# Botones de utilidad para los datos de los clientes
col_buttons = st.columns([1, 1, 4])
with col_buttons[0]:
    if st.button("🔄 Cargar Caso de Estudio 1"):
        st.session_state.clients_df = default_clients.copy()
        st.session_state.depot_name = "CEDI Tocancipá"
        st.session_state.depot_lat = 4.964
        st.session_state.depot_lon = -73.912
        st.rerun()

with col_buttons[1]:
    if st.button("🧹 Limpiar Clientes"):
        st.session_state.clients_df = pd.DataFrame(columns=["Nombre", "Latitud (Y)", "Longitud (X)", "Demanda (kg)"])
        st.rerun()

# Editor interactivo de datos de clientes
st.subheader("📍 Coordenadas y Demanda de los Clientes")
st.markdown("Puedes editar directamente los datos en la tabla, añadir nuevas filas presionando el botón `+` o eliminar filas seleccionándolas y presionando la tecla `Suprimir`.")

edited_df = st.data_editor(
    st.session_state.clients_df,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "Nombre": st.column_config.TextColumn("Nombre del Municipio/Cliente", required=True),
        "Latitud (Y)": st.column_config.NumberColumn("Latitud (Y)", min_value=-4.0, max_value=13.0, format="%.6f", required=True),
        "Longitud (X)": st.column_config.NumberColumn("Longitud (X)", min_value=-82.0, max_value=-66.0, format="%.6f", required=True),
        "Demanda (kg)": st.column_config.NumberColumn("Demanda (kg)", min_value=1, max_value=10000, step=10, required=True),
    }
)
st.session_state.clients_df = edited_df

# Validaciones preliminares antes del cálculo
total_demand = edited_df["Demanda (kg)"].sum() if not edited_df.empty else 0
total_fleet_capacity = num_vehicles * vehicle_capacity

# Alertas visuales de viabilidad física
if total_demand > total_fleet_capacity:
    st.error(f"🚨 **Infactibilidad de Carga:** La demanda acumulada ({total_demand:,} kg) supera la capacidad conjunta de transporte instalada en tu flota ({total_fleet_capacity:,} kg). Agrega más vehículos o reduce la demanda de los clientes.")
elif edited_df.empty:
    st.warning("⚠️ Agrega al menos un cliente a la tabla para calcular la ruta.")
else:
    # ----------------- SECCIÓN DE EJECUCIÓN -----------------
    if st.button("🚀 Ejecutar Algoritmo de Optimización", type="primary", use_container_width=True):
        
        # Estructuración de datos para el solucionador de OR-Tools
        coordenadas = [(st.session_state.depot_lat, st.session_state.depot_lon)]
        nombres = [st.session_state.depot_name]
        demandas = [0]
        
        for idx, row in edited_df.iterrows():
            coordenadas.append((row["Latitud (Y)"], row["Longitud (X)"]))
            nombres.append(row["Nombre"])
            demandas.append(int(row["Demanda (kg)"]))
            
        num_nodos = len(coordenadas)
        matriz_distancias = np.zeros((num_nodos, num_nodos), dtype=int)
        
        # Cálculo dinámico de la matriz de distancias
        for i in range(num_nodos):
            for j in range(num_nodos):
                dist = sf_factor * np.sqrt((coordenadas[i][0] - coordenadas[j][0])**2 + 
                                            (coordenadas[i][1] - coordenadas[j][1])**2)
                matriz_distancias[i][j] = int(round(dist))
                
        # Estructuración del modelo para el solver
        data = {
            'distance_matrix': matriz_distancias.tolist(),
            'demands': demandas,
            'vehicle_capacities': [int(vehicle_capacity)] * int(num_vehicles),
            'num_vehicles': int(num_vehicles),
            'depot': 0
        }
        
        # Resolver el CVRP
        manager = pywrapcp.RoutingIndexManager(len(data['distance_matrix']), data['num_vehicles'], data['depot'])
        routing = pywrapcp.RoutingModel(manager)

        def distance_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return data['distance_matrix'][from_node][to_node]

        transit_callback_index = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

        def demand_callback(from_index):
            from_node = manager.IndexToNode(from_index)
            return data['demands'][from_node]

        demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
        routing.AddDimensionWithVehicleCapacity(
            demand_callback_index,
            0,  # Sin holgura
            data['vehicle_capacities'],
            True,  
            'Capacity'
        )

        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC)
        search_parameters.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH)
        search_parameters.time_limit.seconds = 3

        solution = routing.SolveWithParameters(search_parameters)

        if solution:
            # Procesamiento de la solución estructurada
            total_distance = 0
            rutas_detalladas = []
            colores_rutas = ['blue', 'red', 'green', 'purple', 'orange', 'darkred', 'cadetblue', 'darkpurple']
            
            # Crear mapa interactivo centrado en el CEDI
            m = folium.Map(location=[st.session_state.depot_lat, st.session_state.depot_lon], zoom_start=11)
            
            # Dibujar el marcador del CEDI
            folium.Marker(
                location=[st.session_state.depot_lat, st.session_state.depot_lon],
                popup=f"<b>{st.session_state.depot_name} (DEPÓSITO)</b>",
                icon=folium.Icon(color='red', icon='cloud')
            ).add_to(m)

            for vehicle_id in range(data['num_vehicles']):
                index = routing.Start(vehicle_id)
                route_nodes = []
                route_distance = 0
                route_load = 0
                
                while not routing.IsEnd(index):
                    node_index = manager.IndexToNode(index)
                    route_load += data['demands'][node_index]
                    route_nodes.append(node_index)
                    previous_index = index
                    index = solution.Value(routing.NextVar(index))
                    route_distance += routing.GetArcCostForVehicle(previous_index, index, vehicle_id)
                
                route_nodes.append(manager.IndexToNode(index))  # Retorno al CEDI
                total_distance += route_distance
                
                # Almacenar la secuencia lógica de visitas de este camión
                rutas_detalladas.append({
                    "vehicle": vehicle_id + 1,
                    "nodes": route_nodes,
                    "distance": route_distance / 1000.0,
                    "load": route_load
                })

                # Graficar la trayectoria del vehículo sobre el mapa
                if len(route_nodes) > 2: # Solo dibujar vehículos activos con entregas reales
                    coordenadas_ruta = [coordenadas[n] for n in route_nodes]
                    color = colores_rutas[vehicle_id % len(colores_rutas)]
                    
                    # Dibujar línea con flechas/indicación de ruta
                    folium.PolyLine(
                        coordenadas_ruta, 
                        color=color, 
                        weight=4, 
                        opacity=0.85,
                        tooltip=f"Ruta Camión {vehicle_id + 1}"
                    ).add_to(m)
                    
                    # Agregar marcadores a los clientes de esta ruta
                    for n in route_nodes[1:-1]:
                        folium.Marker(
                            location=coordenadas[n],
                            popup=f"<b>Cliente:</b> {nombres[n]}<br><b>Demanda:</b> {data['demands'][n]} kg<br><b>Asignado a:</b> Camión {vehicle_id + 1}",
                            icon=folium.Icon(color=color, icon='info-sign')
                        ).add_to(m)

            # ----------------- DESPLIEGUE DE RESULTADOS EN LA APP -----------------
            st.success("✅ ¡Optimización completada con éxito!")
            
            # Métricas en columnas atractivas
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown(f"""
                <div class="metric-card">
                    <p style="margin:0;font-size:14px;color:#6B7280;text-transform:uppercase;">Distancia Total de la Operación</p>
                    <p style="margin:0;font-size:28px;font-weight:bold;color:#1E3A8A;">{total_distance / 1000.0:.2f} km</p>
                </div>
                """, unsafe_allow_html=True)
            with col2:
                vehiculos_activos = sum(1 for r in rutas_detalladas if len(r["nodes"]) > 2)
                st.markdown(f"""
                <div class="metric-card">
                    <p style="margin:0;font-size:14px;color:#6B7280;text-transform:uppercase;">Camiones Requeridos</p>
                    <p style="margin:0;font-size:28px;font-weight:bold;color:#1E3A8A;">{vehiculos_activos} / {num_vehicles} activos</p>
                </div>
                """, unsafe_allow_html=True)
            with col3:
                st.markdown(f"""
                <div class="metric-card" style="border-left-color: #10B981;">
                    <p style="margin:0;font-size:14px;color:#6B7280;text-transform:uppercase;">Carga Total Despachada</p>
                    <p style="margin:0;font-size:28px;font-weight:bold;color:#10B981;">{total_demand:,} kg</p>
                </div>
                """, unsafe_allow_html=True)

            st.write("")

            col_map, col_details = st.columns([5, 4])
            
            with col_map:
                st.subheader("🗺️ Mapa de Trayectorias de Distribución")
                # Renderizar el mapa de Folium interactivo usando HTML
                map_html = m._repr_html_()
                st.components.v1.html(map_html, height=520, scrolling=False)
                
            with col_details:
                st.subheader("📋 Plan de Despacho Detallado")
                for r in rutas_detalladas:
                    if len(r["nodes"]) > 2:
                        color_box = colores_rutas[(r["vehicle"] - 1) % len(colores_rutas)]
                        with st.expander(f"🚛 Camión {r['vehicle']} — {r['distance']:.2f} km — Carga: {r['load']:,} kg", expanded=True):
                            # Construir el flujo gráfico
                            pasos = [f"**{nombres[n]}**" for n in r["nodes"]]
                            st.write(" ➡️ ".join(pasos))
                            st.progress(min(1.0, r['load'] / vehicle_capacity), text=f"Capacidad ocupada: {r['load']}/{vehicle_capacity} kg")
                    else:
                        st.info(f"💤 Camión {r['vehicle']} — No requerido en este despacho (Permanecerá en el depósito).")
        else:
            st.error("❌ El solucionador matemático determinó que el problema no tiene solución factible con la flota y capacidades ingresadas. Intenta aumentando la cantidad de camiones o su capacidad.")
