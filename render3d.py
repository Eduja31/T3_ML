"""
render3d.py
==============================================================
Todo el dibujo en 3D con PyOpenGL (OpenGL clásico / fixed-function
pipeline, ideal para un prototipo académico: cubos, cilindros y
esferas con glBegin/glEnd, luces e iluminación básica).
==============================================================
"""

import math
import random
import time

from OpenGL.GL import *
from OpenGL.GLU import *


# ------------------------------------------------------------------
def init_gl(width, height):
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_LIGHTING)
    glEnable(GL_LIGHT0)
    glEnable(GL_COLOR_MATERIAL)
    glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)

    glLightfv(GL_LIGHT0, GL_POSITION, [20.0, 30.0, 10.0, 1.0])
    glLightfv(GL_LIGHT0, GL_AMBIENT, [0.25, 0.30, 0.35, 1.0])
    glLightfv(GL_LIGHT0, GL_DIFFUSE, [0.85, 0.90, 0.95, 1.0])

    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    glClearColor(0.02, 0.04, 0.08, 1.0)
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(55, width / height, 0.1, 500.0)
    glMatrixMode(GL_MODELVIEW)


def resize(width, height):
    glViewport(0, 0, width, height)
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(55, width / max(height, 1), 0.1, 500.0)
    glMatrixMode(GL_MODELVIEW)


# ------------------------------------------------------------------
#  PRIMITIVAS BÁSICAS
# ------------------------------------------------------------------
def draw_box(w, h, d, color, wireframe=False):
    """Dibuja una caja centrada en el origen, tamaño w (x) h (y) d (z)."""
    glColor4f(*color, 1.0 if not wireframe else 0.6)
    x, y, z = w / 2, h / 2, d / 2
    mode = GL_LINE_LOOP if wireframe else GL_QUADS
    if wireframe:
        glDisable(GL_LIGHTING)

    faces = [
        [(-x, -y, z), (x, -y, z), (x, y, z), (-x, y, z)],     # frente
        [(-x, -y, -z), (-x, y, -z), (x, y, -z), (x, -y, -z)],  # atrás
        [(-x, -y, -z), (-x, -y, z), (-x, y, z), (-x, y, -z)],  # izquierda
        [(x, -y, -z), (x, y, -z), (x, y, z), (x, -y, z)],      # derecha
        [(-x, y, -z), (-x, y, z), (x, y, z), (x, y, -z)],      # arriba
        [(-x, -y, -z), (x, -y, -z), (x, -y, z), (-x, -y, z)],  # abajo
    ]
    normals = [(0,0,1), (0,0,-1), (-1,0,0), (1,0,0), (0,1,0), (0,-1,0)]

    for face, n in zip(faces, normals):
        if not wireframe:
            glNormal3f(*n)
        glBegin(mode)
        for v in face:
            glVertex3f(*v)
        glEnd()

    if wireframe:
        glEnable(GL_LIGHTING)


def draw_cylinder(radius_top, radius_bottom, height, color, slices=12):
    glColor4f(*color, 1.0)
    quad = gluNewQuadric()
    gluQuadricNormals(quad, GLU_SMOOTH)
    glPushMatrix()
    glRotatef(-90, 1, 0, 0)
    gluCylinder(quad, radius_bottom, radius_top, height, slices, 1)
    glPopMatrix()
    gluDeleteQuadric(quad)


def draw_sphere(radius, color, slices=10, stacks=10):
    glColor4f(*color, 0.85)
    quad = gluNewQuadric()
    gluQuadricNormals(quad, GLU_SMOOTH)
    gluSphere(quad, radius, slices, stacks)
    gluDeleteQuadric(quad)


def draw_grid(size=60, step=3, color=(0.0, 0.9, 1.0, 0.06)):
    glDisable(GL_LIGHTING)
    glColor4f(*color)
    glBegin(GL_LINES)
    n = size // step
    for i in range(-n, n + 1):
        glVertex3f(i * step, 0.01, -size)
        glVertex3f(i * step, 0.01, size)
        glVertex3f(-size, 0.01, i * step)
        glVertex3f(size, 0.01, i * step)
    glEnd()
    glEnable(GL_LIGHTING)


def draw_text_billboard_placeholder():
    """(El texto 2D real se dibuja aparte con pygame, ver ui_overlay.py)"""
    pass


# ------------------------------------------------------------------
#  ESCENA COMPLETA
# ------------------------------------------------------------------
class Escena3D:
    def __init__(self, zonas):
        self.zonas = zonas
        self.t0 = time.time()
        self.gotas_agua = []   # partículas de agua activas: [x,y,z,vy,vida]

    # ----------------------------------------------------------
    def dibujar(self, zona_seleccionada, riego_activo, zonas_auto):
        t = time.time() - self.t0

        # Suelo
        glPushMatrix()
        draw_box(60, 0.2, 60, (0.10, 0.18, 0.10))
        glPopMatrix()
        draw_grid()

        # Zonas de cultivo
        for z in self.zonas:
            self._dibujar_zona(z, t, z.id == zona_seleccionada)

        # Edificio de control central
        self._dibujar_estacion_control(t)

        # Tuberías
        for z in self.zonas:
            self._dibujar_tuberia(z)

        # Partículas de agua
        self._actualizar_y_dibujar_agua()

        # Spawnea gotas si hay riego en zonas activas
        for z in self.zonas:
            activa = riego_activo or z.id in zonas_auto
            if activa and random.random() < 0.45:
                self._spawn_gota(z)

    # ----------------------------------------------------------
    def _dibujar_zona(self, z, t, seleccionada):
        glPushMatrix()
        flotacion = math.sin(t * 0.5 + z.id) * 0.02
        glTranslatef(z.pos[0], 0.15 + flotacion, z.pos[1])

        color = z.color_estado()
        opacidad_extra = 0.3 if seleccionada else 0.0
        glPushMatrix()
        glScalef(z.tam[0], 1, z.tam[1])
        draw_box(1, 0.05, 1, color)
        glPopMatrix()

        # Borde resaltado si está seleccionada
        if seleccionada:
            glPushMatrix()
            glScalef(z.tam[0] + 0.3, 1.3, z.tam[1] + 0.3)
            draw_box(1, 0.08, 1, (1.0, 1.0, 1.0), wireframe=True)
            glPopMatrix()

        # Cultivos (pequeños conos/cilindros verdes)
        for cx in range(-3, 4, 2):
            for cz in range(-3, 4, 2):
                glPushMatrix()
                glTranslatef(cx * 0.9, 0.05, cz * 0.9)
                glColor3f(0.2, 0.5, 0.2)
                draw_cylinder(0.05, 0.18, 0.6, (0.16, 0.45, 0.2))
                glPopMatrix()

        glPopMatrix()

        # Poste de sensor ESP32 (fuera del bloque de flotación, posición fija)
        sx, sz = z.pos[0] - 3.5, z.pos[1] - 3.5
        glPushMatrix()
        glTranslatef(sx, 0, sz)
        draw_cylinder(0.05, 0.05, 1.5, (0.7, 0.74, 0.77))
        glTranslatef(0, 1.5, 0)
        draw_box(0.3, 0.3, 0.3, (0.15, 0.18, 0.21))
        # luz pulsante del sensor
        pulso = 0.5 + 0.5 * math.sin(t * 2 + z.id)
        glPushMatrix()
        glTranslatef(0, 0.3, 0)
        draw_sphere(0.08 + pulso * 0.04, z.color_estado())
        glPopMatrix()
        glPopMatrix()

    # ----------------------------------------------------------
    def _dibujar_estacion_control(self, t):
        glPushMatrix()
        glTranslatef(0, 1.5, 0)
        draw_box(4, 3, 3, (0.15, 0.18, 0.21))
        glPopMatrix()

        # Pantalla
        glPushMatrix()
        glTranslatef(0, 1.2, 1.52)
        flicker = 0.8 + 0.2 * math.sin(t * 3)
        draw_box(0.8, 2, 0.05, (0.0, 0.69 * flicker, 1.0 * flicker))
        glPopMatrix()

        # Antena giratoria
        glPushMatrix()
        glTranslatef(0, 3.5, 0)
        glRotatef((t * 60) % 360, 0, 1, 0)
        draw_cylinder(0.03, 0.03, 1.2, (0.7, 0.74, 0.77))
        glPopMatrix()

    # ----------------------------------------------------------
    def _dibujar_tuberia(self, z):
        glPushMatrix()
        x, zp = z.pos[0] * 0.5, z.pos[1] * 0.5
        dist = math.hypot(z.pos[0], z.pos[1]) - 2
        ang = math.degrees(math.atan2(z.pos[0], z.pos[1]))
        glTranslatef(x, 0.08, zp)
        glRotatef(ang, 0, 1, 0)
        glRotatef(90, 1, 0, 0)
        draw_cylinder(0.08, 0.08, dist, (0.33, 0.43, 0.48))
        glPopMatrix()

    # ----------------------------------------------------------
    def _spawn_gota(self, z):
        x = z.pos[0] + random.uniform(-4, 4)
        zc = z.pos[1] + random.uniform(-3.5, 3.5)
        self.gotas_agua.append([x, 3.0 + random.uniform(0, 2), zc, 0.0, 0])

    def _actualizar_y_dibujar_agua(self):
        nuevas = []
        for gota in self.gotas_agua:
            gota[3] -= 0.012          # gravedad (vy)
            gota[1] += gota[3]        # y += vy
            gota[4] += 1              # vida++
            if gota[1] > 0.1 and gota[4] < 90:
                nuevas.append(gota)
                glPushMatrix()
                glTranslatef(gota[0], gota[1], gota[2])
                draw_sphere(0.1, (0.16, 0.71, 0.96))
                glPopMatrix()
        self.gotas_agua = nuevas
