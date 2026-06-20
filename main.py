"""
main.py
==============================================================
SISTEMA DE GESTIÓN HÍDRICA INTELIGENTE — Prototipo 3D en Python
==============================================================
Motor: Pygame + PyOpenGL (fixed-function pipeline)

Controles:
  - Click izquierdo + arrastrar  -> rotar cámara
  - Rueda del mouse               -> zoom
  - Click sobre una zona          -> seleccionarla
  - Teclas 1-4                    -> seleccionar zona directamente
  - R                              -> activar/desactivar riego manual
  - A                              -> activar/desactivar modo automático
  - P                              -> ejecutar predicción ML
  - X                              -> simular estrés hídrico aleatorio
  - TAB                            -> abrir/cerrar panel de Reportes
  - ESC / cerrar ventana           -> salir

Para correr:
  pip install -r requirements.txt
  python main.py
==============================================================
"""

import math
import sys
import time

import pygame
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *

from data_model import (
    crear_zonas_iniciales, HistorialDatos,
    UMBRAL_CRITICO, UMBRAL_BAJO, UMBRAL_PARAR, UMBRAL_EXCESO,
)
from alerts import GestorAlertas
from render3d import init_gl, resize, Escena3D
from ui_overlay import (
    UIOverlay, CYAN, TEAL, WHITE, GREY, GREEN, ORANGE, RED, PURPLE, BG_PANEL,
)

WIDTH, HEIGHT = 1280, 800
LEFT_PANEL_W = 260
RIGHT_PANEL_W = 260
TOPBAR_H = 52
STATUSBAR_H = 32


# ======================================================================
class App:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Sistema de Gestión Hídrica Inteligente — Prototipo 3D")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT), DOUBLEBUF | OPENGL | RESIZABLE)
        self.clock = pygame.time.Clock()
        self.width, self.height = WIDTH, HEIGHT

        init_gl(self.width, self.height)
        self.ui = UIOverlay(self.width, self.height)

        # --- Modelo de datos ---
        self.zonas = crear_zonas_iniciales()
        self.historial = HistorialDatos(self.zonas)
        self.alertas = GestorAlertas()
        self.escena = Escena3D(self.zonas)

        # --- Estado de interacción ---
        self.zona_seleccionada = None
        self.riego_manual = False
        self.modo_auto = False
        self.mostrar_reportes = False
        self.agua_ahorrada = 0.0
        self.sync_min = 0

        # Sliders (igual que en la versión web)
        self.umbral_humedad = 45
        self.caudal = 3.2
        self.intervalo_pred = 24
        self.precision_ml_min = 75

        # --- Cámara orbital ---
        self.cam_theta = math.pi / 4
        self.cam_phi = math.pi / 4.5
        self.cam_radius = 42
        self.dragging = False
        self.last_mouse = (0, 0)

        self.running = True
        self.last_sim_tick = time.time()
        self.last_clock_tick = time.time()

        self.alertas.lanzar("info", "📡", "Sistema en Línea",
                             "Todos los sensores ESP32 conectados. Monitoreo activo en 4 zonas.", duracion=5)

    # ------------------------------------------------------------------
    def run(self):
        while self.running:
            self._handle_events()
            self._update()
            self._render()
            self.clock.tick(60)
        pygame.quit()
        sys.exit()

    # ------------------------------------------------------------------
    #  EVENTOS / INPUT
    # ------------------------------------------------------------------
    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == QUIT:
                self.running = False

            elif event.type == VIDEORESIZE:
                self.width, self.height = event.w, event.h
                resize(self.width, self.height)
                self.ui.resize(self.width, self.height)

            elif event.type == KEYDOWN:
                self._handle_keydown(event.key)

            elif event.type == MOUSEBUTTONDOWN:
                if event.button == 1:
                    if not self._click_en_ui(event.pos):
                        self.dragging = True
                        self.last_mouse = event.pos
                        self._intentar_seleccionar_zona(event.pos)
                elif event.button == 4:
                    self.cam_radius = max(15, self.cam_radius - 2)
                elif event.button == 5:
                    self.cam_radius = min(70, self.cam_radius + 2)

            elif event.type == MOUSEBUTTONUP:
                if event.button == 1:
                    self.dragging = False

            elif event.type == MOUSEMOTION:
                if self.dragging:
                    dx = event.pos[0] - self.last_mouse[0]
                    dy = event.pos[1] - self.last_mouse[1]
                    self.cam_theta -= dx * 0.005
                    self.cam_phi = max(0.15, min(1.4, self.cam_phi - dy * 0.005))
                    self.last_mouse = event.pos

    def _handle_keydown(self, key):
        if key == K_ESCAPE:
            self.running = False
        elif key in (K_1, K_2, K_3, K_4):
            self.seleccionar_zona(int(key) - K_1)
        elif key == K_r:
            self.toggle_riego_manual()
        elif key == K_a:
            self.toggle_modo_auto()
        elif key == K_p:
            self.ejecutar_prediccion_ml()
        elif key == K_x:
            self.simular_estres_aleatorio()
        elif key == K_TAB:
            self.mostrar_reportes = not self.mostrar_reportes

    def _click_en_ui(self, pos):
        """True si el click cayó dentro de algún panel lateral (para no rotar cámara)."""
        x, y = pos
        if x < LEFT_PANEL_W or x > self.width - RIGHT_PANEL_W:
            return True
        if y < TOPBAR_H + STATUSBAR_H:
            return True
        return False

    def _intentar_seleccionar_zona(self, pos):
        """
        Selección simplificada por proyección: probamos cuál zona está
        más cerca del rayo de cámara -> mouse, proyectando sobre el plano y=0.
        (Una alternativa simple y educativa al picking con buffers de color.)
        """
        x, y = pos
        if self._click_en_ui(pos):
            return

        # Reconstruir el rayo cámara->mundo de forma aproximada:
        # usamos gluUnProject con la matriz actual.
        viewport = glGetIntegerv(GL_VIEWPORT)
        modelview = glGetDoublev(GL_MODELVIEW_MATRIX)
        projection = glGetDoublev(GL_PROJECTION_MATRIX)

        win_y = viewport[3] - y
        near = gluUnProject(x, win_y, 0.0, modelview, projection, viewport)
        far = gluUnProject(x, win_y, 1.0, modelview, projection, viewport)

        # Intersección del rayo con el plano y=0
        if far[1] == near[1]:
            return
        t = -near[1] / (far[1] - near[1])
        px = near[0] + t * (far[0] - near[0])
        pz = near[2] + t * (far[2] - near[2])

        for z in self.zonas:
            hx, hz = z.tam[0] / 2, z.tam[1] / 2
            if (z.pos[0] - hx <= px <= z.pos[0] + hx) and (z.pos[1] - hz <= pz <= z.pos[1] + hz):
                self.seleccionar_zona(z.id)
                return

    # ------------------------------------------------------------------
    #  ACCIONES (equivalentes a los botones de la versión web)
    # ------------------------------------------------------------------
    def seleccionar_zona(self, zid):
        self.zona_seleccionada = zid
        z = self.zonas[zid]
        self.alertas.registrar_evento(f"Zona {z.nombre} seleccionada")

    def toggle_riego_manual(self):
        self.riego_manual = not self.riego_manual
        if self.riego_manual:
            self.alertas.lanzar("info", "💧", "Riego Manual Activado",
                                 "Electroválvulas abiertas en todas las zonas.", duracion=5)
        else:
            self.alertas.lanzar("ok", "🛑", "Riego Detenido",
                                 "Electroválvulas cerradas. Monitoreo continúa.", duracion=4)

    def toggle_modo_auto(self):
        self.modo_auto = not self.modo_auto
        self.alertas.modo_auto = self.modo_auto
        if self.modo_auto:
            self.alertas.lanzar("auto", "🤖", "Modo Automático Activado",
                                 f"El sistema regará solo si la humedad cae bajo {UMBRAL_CRITICO}%.", duracion=6)
        else:
            self.alertas.zonas_riego_auto.clear()
            self.alertas.lanzar("info", "👤", "Modo Manual Activado",
                                 "El riego ahora requiere tu intervención.", duracion=4)

    def ejecutar_prediccion_ml(self):
        import random
        precision = self.historial.precision_modelo_simulada()
        self.alertas.lanzar("info", "🤖", "Predicción ML Ejecutada",
                             f"Modelo ejecutado con {precision}% de precisión estimada.", duracion=5)
        for z in self.zonas:
            z.humedad = max(20, min(95, z.humedad + random.uniform(-5, 5)))

    def simular_estres_aleatorio(self):
        import random
        zid = random.randint(0, len(self.zonas) - 1)
        self.zonas[zid].humedad = 22
        self.alertas.ya_mostradas.discard(f"critico_{zid}")
        self.alertas.registrar_evento(f"⚠ Estrés hídrico simulado en {self.zonas[zid].nombre}")

    # ------------------------------------------------------------------
    #  UPDATE / SIMULACIÓN
    # ------------------------------------------------------------------
    def _update(self):
        import random
        ahora = time.time()

        if ahora - self.last_sim_tick >= 2.0:
            self.last_sim_tick = ahora
            self.sync_min += 1

            for z in self.zonas:
                drift = random.uniform(-0.4, 0.35)
                z.humedad = max(15, min(95, z.humedad + drift))
                riega = self.riego_manual or (self.modo_auto and z.id in self.alertas.zonas_riego_auto)
                if riega:
                    z.humedad = min(95, z.humedad + 0.5)

            if self.riego_manual or self.alertas.zonas_riego_auto:
                self.agua_ahorrada += 0.05

            self.historial.registrar_lectura()
            self.alertas.evaluar_zonas(self.zonas, self.riego_manual)

        self.alertas.limpiar_expiradas()

    # ------------------------------------------------------------------
    #  RENDER
    # ------------------------------------------------------------------
    def _render(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()

        # Cámara orbital
        cx = self.cam_radius * math.sin(self.cam_phi) * math.sin(self.cam_theta)
        cy = self.cam_radius * math.cos(self.cam_phi)
        cz = self.cam_radius * math.sin(self.cam_phi) * math.cos(self.cam_theta)
        gluLookAt(cx, cy, cz, 0, 0, 0, 0, 1, 0)

        self.escena.dibujar(self.zona_seleccionada, self.riego_manual, self.alertas.zonas_riego_auto)

        # ---- Overlay 2D ----
        self.ui.iniciar_modo_2d()
        self._dibujar_topbar()
        self._dibujar_statusbar()
        self._dibujar_panel_izquierdo()
        self._dibujar_panel_derecho()
        self._dibujar_alertas()
        if self.mostrar_reportes:
            self._dibujar_panel_reportes()
        self.ui.terminar_modo_2d()

        pygame.display.flip()

    # ------------------------------------------------------------------
    #  PANELES UI
    # ------------------------------------------------------------------
    def _dibujar_topbar(self):
        self.ui.draw_rect(0, 0, self.width, TOPBAR_H, (13, 33, 55, 240))
        self.ui.draw_text("● SISTEMA DE GESTIÓN HÍDRICA INTELIGENTE", 16, 10, self.ui.font_med, CYAN)
        self.ui.draw_text("Monitoreo en Tiempo Real · IoT + ML · ESP32 (Python/OpenGL)", 16, 30, self.ui.font_small, TEAL)

        reloj = time.strftime("%d/%m/%Y · %H:%M:%S")
        self.ui.draw_text(reloj, self.width - 180, 18, self.ui.font_small, TEAL)

        if self.modo_auto:
            self.ui.draw_rect(self.width - 420, 12, 200, 28, (26, 0, 64, 220))
            self.ui.draw_text("🤖 RIEGO AUTOMÁTICO ACTIVO", self.width - 410, 18, self.ui.font_small, PURPLE)

        if self.mostrar_reportes:
            self.ui.draw_text("[TAB] Cerrar Reportes", self.width // 2 - 70, 18, self.ui.font_small, ORANGE)
        else:
            self.ui.draw_text("[TAB] Ver Reportes", self.width // 2 - 60, 18, self.ui.font_small, TEAL)

    def _dibujar_statusbar(self):
        y = TOPBAR_H
        self.ui.draw_rect(LEFT_PANEL_W, y, self.width - LEFT_PANEL_W - RIGHT_PANEL_W, STATUSBAR_H, (8, 14, 26, 255))

        estado_txt, estado_color_f = self.alertas.estado_global(self.zonas)
        estado_color = tuple(int(c * 255) for c in estado_color_f)
        avg_hum = sum(z.humedad for z in self.zonas) / len(self.zonas)
        modo_txt = "AUTOMÁTICO" if self.modo_auto else "MANUAL"
        riega = self.riego_manual or bool(self.alertas.zonas_riego_auto)
        riego_txt = "ACTIVO" if self.riego_manual else (
            f"AUTO ({len(self.alertas.zonas_riego_auto)})" if self.alertas.zonas_riego_auto else "DETENIDO")

        segs_w = (self.width - LEFT_PANEL_W - RIGHT_PANEL_W) / 5
        base_x = LEFT_PANEL_W

        items = [
            (f"Estado: {estado_txt}", estado_color),
            (f"Humedad Prom: {avg_hum:.1f}%", CYAN),
            (f"Modo: {modo_txt}", PURPLE),
            (f"Riego: {riego_txt}", CYAN if riega else GREY),
            (f"Alertas: {len(self.alertas.alertas_activas)}", ORANGE),
        ]
        for i, (txt, color) in enumerate(items):
            self.ui.draw_text(txt, base_x + i * segs_w + 14, y + 9, self.ui.font_small, color)

    # ------------------------------------------------------------------
    def _dibujar_panel_izquierdo(self):
        x0, y0 = 0, TOPBAR_H + STATUSBAR_H
        h = self.height - y0
        self.ui.draw_rect(x0, y0, LEFT_PANEL_W, h, (13, 27, 42, 235))

        y = y0 + 14
        self.ui.draw_text("ZONAS DE CULTIVO", x0 + 16, y, self.ui.font_small, CYAN)
        y += 22

        for z in self.zonas:
            seleccionada = z.id == self.zona_seleccionada
            card_color = (13, 45, 74, 255) if seleccionada else (19, 35, 56, 255)
            self.ui.draw_rect(x0 + 10, y, LEFT_PANEL_W - 20, 64, card_color)
            if seleccionada:
                self.ui.draw_rect_border(x0 + 10, y, LEFT_PANEL_W - 20, 64, CYAN)

            color_estado = tuple(int(c * 255) for c in z.color_estado())
            self.ui.draw_text(z.nombre, x0 + 18, y + 6, self.ui.font_med, WHITE)
            self.ui.draw_text(f"🌱 {z.cultivo}", x0 + 18, y + 24, self.ui.font_small, TEAL)
            self.ui.draw_text(f"💧{z.humedad:.0f}%  🌡{z.temperatura:.1f}°C", x0 + 18, y + 42, self.ui.font_small, color_estado)
            self.ui.draw_bar(x0 + 18, y + 58, LEFT_PANEL_W - 36, 4, z.humedad, color_estado)

            y += 72

        y += 10
        self.ui.draw_text("CONTROL DE RIEGO", x0 + 16, y, self.ui.font_small, CYAN)
        y += 22
        sliders = [
            (f"Umbral de Humedad: {self.umbral_humedad}%", self.umbral_humedad),
            (f"Caudal de Riego: {self.caudal:.1f} L/min", self.caudal * 10),
            (f"Intervalo Predicción: {self.intervalo_pred}h", self.intervalo_pred * 2),
            (f"Precisión ML Mínima: {self.precision_ml_min}%", self.precision_ml_min),
        ]
        for label, val in sliders:
            self.ui.draw_text(label, x0 + 16, y, self.ui.font_small, TEAL)
            y += 16
            self.ui.draw_bar(x0 + 16, y, LEFT_PANEL_W - 32, 4, min(val, 100), CYAN)
            y += 18

        y += 10
        self.ui.draw_text("ACCIONES  (teclas)", x0 + 16, y, self.ui.font_small, CYAN)
        y += 22
        btn_riego_txt = "⛔ [R] Detener Riego Manual" if self.riego_manual else "💧 [R] Activar Riego Manual"
        btn_auto_txt = "⏹ [A] Desactivar Auto" if self.modo_auto else "🔄 [A] Activar Modo Automático"
        acciones = [
            (btn_riego_txt, GREEN if not self.riego_manual else RED),
            ("🤖 [P] Ejecutar Predicción ML", CYAN),
            ("⚠️ [X] Simular Estrés Hídrico", ORANGE),
            (btn_auto_txt, PURPLE),
        ]
        for txt, color in acciones:
            self.ui.draw_rect(x0 + 10, y, LEFT_PANEL_W - 20, 24, (*[int(c*0.25) for c in color], 255))
            self.ui.draw_text(txt, x0 + 16, y + 5, self.ui.font_small, color)
            y += 30

        y += 10
        self.ui.draw_text("SISTEMA", x0 + 16, y, self.ui.font_small, CYAN)
        y += 20
        info_sistema = [
            ("Nodos ESP32", "4 / 4 ✓", GREEN),
            ("Cloud (Firebase)", "Online", GREEN),
            ("Último sync", f"hace {self.sync_min} min", TEAL),
            ("Agua ahorrada", f"{self.agua_ahorrada:.1f} L", CYAN),
        ]
        for label, val, color in info_sistema:
            self.ui.draw_text(label, x0 + 16, y, self.ui.font_small, TEAL)
            self.ui.draw_text(val, x0 + LEFT_PANEL_W - 16 - len(val) * 7, y, self.ui.font_small, color)
            y += 18

    # ------------------------------------------------------------------
    def _dibujar_panel_derecho(self):
        x0 = self.width - RIGHT_PANEL_W
        y0 = TOPBAR_H + STATUSBAR_H
        h = self.height - y0
        self.ui.draw_rect(x0, y0, RIGHT_PANEL_W, h, (13, 27, 42, 235))

        y = y0 + 14
        self.ui.draw_text("ZONA SELECCIONADA", x0 + 16, y, self.ui.font_small, CYAN)
        y += 24

        if self.zona_seleccionada is None:
            self.ui.draw_text("Haz clic en una zona", x0 + 16, y, self.ui.font_small, GREY)
            self.ui.draw_text("del campo 3D, o pulsa", x0 + 16, y + 16, self.ui.font_small, GREY)
            self.ui.draw_text("las teclas 1-4.", x0 + 16, y + 32, self.ui.font_small, GREY)
            y += 60
        else:
            z = self.zonas[self.zona_seleccionada]
            color_estado = tuple(int(c * 255) for c in z.color_estado())
            self.ui.draw_rect(x0 + 10, y, RIGHT_PANEL_W - 20, 90, (19, 35, 56, 255))
            self.ui.draw_text(f"{z.nombre} · {z.cultivo}", x0 + 18, y + 8, self.ui.font_med, WHITE)
            self.ui.draw_text(f"Humedad: {z.humedad:.0f}%", x0 + 18, y + 30, self.ui.font_small, CYAN)
            self.ui.draw_text(f"Temp: {z.temperatura:.1f}°C", x0 + 18, y + 46, self.ui.font_small, ORANGE)
            self.ui.draw_text(f"Estado: {z.estado()}", x0 + 18, y + 62, self.ui.font_small, color_estado)
            y += 100

            valvula_abierta = self.riego_manual or z.id in self.alertas.zonas_riego_auto
            self.ui.draw_text("Electroválvula:", x0 + 16, y, self.ui.font_small, TEAL)
            self.ui.draw_text("Abierta" if valvula_abierta else "Cerrada", x0 + 150, y,
                               self.ui.font_small, GREEN if valvula_abierta else GREY)
            y += 26

            # Predicción ML simple (regresión lineal con numpy)
            self.ui.draw_text("PREDICCIÓN ML (48h)", x0 + 16, y, self.ui.font_small, CYAN)
            y += 20
            pron = self.historial.pronostico_lineal(z.id)
            for horas, valor in pron:
                col = CYAN if valor > 60 else (ORANGE if valor > 40 else RED)
                self.ui.draw_text(f"+{horas}h", x0 + 16, y, self.ui.font_small, TEAL)
                self.ui.draw_bar(x0 + 50, y + 4, 130, 6, valor, col)
                self.ui.draw_text(f"{valor:.0f}%", x0 + 190, y, self.ui.font_small, WHITE)
                y += 18
            y += 10

        self.ui.draw_text("REGISTRO DE EVENTOS", x0 + 16, y, self.ui.font_small, CYAN)
        y += 20
        for hora, texto in self.alertas.eventos_log[:8]:
            self.ui.draw_text(f"{hora}", x0 + 16, y, self.ui.font_small, GREY)
            texto_corto = texto if len(texto) < 28 else texto[:26] + "…"
            self.ui.draw_text(texto_corto, x0 + 16, y + 14, self.ui.font_small, WHITE)
            y += 30

    # ------------------------------------------------------------------
    def _dibujar_alertas(self):
        ancho = 440
        x = (self.width - ancho) // 2
        y = TOPBAR_H + STATUSBAR_H + 10

        for alerta in self.alertas.alertas_activas[-4:]:
            color = tuple(int(c * 255) for c in alerta.color())
            self.ui.draw_rect(x, y, ancho, 56, (*[int(c * 0.18) for c in color], 235))
            self.ui.draw_rect_border(x, y, ancho, 56, color)
            self.ui.draw_text(f"{alerta.icono}  {alerta.titulo}", x + 12, y + 8, self.ui.font_med, color)
            mensaje_corto = alerta.mensaje if len(alerta.mensaje) < 64 else alerta.mensaje[:62] + "…"
            self.ui.draw_text(mensaje_corto, x + 12, y + 30, self.ui.font_small, WHITE)

            # barra de progreso (tiempo restante)
            restante = 1.0 - alerta.progreso()
            self.ui.draw_bar(x + 4, y + 50, ancho - 8, 3, restante * 100, color)
            y += 64

    # ------------------------------------------------------------------
    def _dibujar_panel_reportes(self):
        x0, y0 = LEFT_PANEL_W, TOPBAR_H + STATUSBAR_H
        w = self.width - LEFT_PANEL_W - RIGHT_PANEL_W
        h = self.height - y0
        self.ui.draw_rect(x0, y0, w, h, (8, 14, 26, 245))

        y = y0 + 24
        self.ui.draw_text("📊 PANEL DE REPORTES DEL PROYECTO", x0 + w//2 - 160, y, self.ui.font_big, CYAN)
        y += 40

        # KPIs principales
        precision = self.historial.precision_modelo_simulada()
        kpis = [
            ("Reducción de Agua", "20%", GREEN),
            ("Precisión ML actual", f"{precision}%", CYAN),
            ("Frecuencia muestreo", "15 min", TEAL),
            ("Horizonte predictivo", "48 h", PURPLE),
        ]
        kx = x0 + 20
        for label, val, color in kpis:
            self.ui.draw_rect(kx, y, 180, 80, (19, 35, 56, 255))
            self.ui.draw_text(val, kx + 16, y + 14, self.ui.font_big, color)
            self.ui.draw_text(label, kx + 16, y + 46, self.ui.font_small, TEAL)
            kx += 196
        y += 100

        # Tabla estadística por zona (pandas)
        self.ui.draw_text("ANÁLISIS ESTADÍSTICO POR ZONA (pandas)", x0 + 20, y, self.ui.font_med, CYAN)
        y += 24
        stats = self.historial.estadisticas_por_zona()
        headers = ["Zona", "Hum.Media", "Desv.Std", "Mín", "Máx", "Temp.Media", "% Tiempo Crítico"]
        col_w = [150, 110, 100, 80, 80, 110, 140]
        cx = x0 + 20
        for hdr, cw in zip(headers, col_w):
            self.ui.draw_text(hdr, cx, y, self.ui.font_small, ORANGE)
            cx += cw
        y += 20

        if not stats.empty:
            for zona_nombre, row in stats.iterrows():
                cx = x0 + 20
                valores = [
                    zona_nombre,
                    f"{row['humedad_media']:.1f}%",
                    f"{row['humedad_std']:.2f}",
                    f"{row['humedad_min']:.0f}%",
                    f"{row['humedad_max']:.0f}%",
                    f"{row['temp_media']:.1f}°C",
                    f"{row['pct_tiempo_critico']:.1f}%",
                ]
                for val, cw in zip(valores, col_w):
                    self.ui.draw_text(str(val), cx, y, self.ui.font_small, WHITE)
                    cx += cw
                y += 20
        y += 20

        # Anomalías detectadas (z-score) de la zona seleccionada
        zid_para_analisis = self.zona_seleccionada if self.zona_seleccionada is not None else 0
        self.ui.draw_text(
            f"ANOMALÍAS DETECTADAS — {self.zonas[zid_para_analisis].nombre} (z-score > 2.0)",
            x0 + 20, y, self.ui.font_med, CYAN)
        y += 24
        anomalas = self.historial.detectar_anomalias(zid_para_analisis)
        if anomalas.empty:
            self.ui.draw_text("Sin anomalías significativas detectadas en el historial.", x0 + 20, y, self.ui.font_small, GREY)
            y += 20
        else:
            for _, row in anomalas.tail(6).iterrows():
                ts = row["datetime"].strftime("%d/%m %H:%M")
                txt = f"{ts}  →  humedad {row['humedad']:.1f}%   (z={row['z_score']:.2f})"
                self.ui.draw_text(txt, x0 + 20, y, self.ui.font_small, RED)
                y += 18

        y += 14
        self.ui.draw_text(
            "Fuente de datos: simulación de lecturas de sensores ESP32 cada 15 min (random-walk), "
            "almacenadas en memoria como si vinieran de Firebase. El módulo data_model.py expone "
            "estadísticas_por_zona(), detectar_anomalias() y pronostico_lineal() usando pandas y numpy.",
            x0 + 20, self.height - 50, self.ui.font_small, GREY)


# ======================================================================
if __name__ == "__main__":
    app = App()
    app.run()
