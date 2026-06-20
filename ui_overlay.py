"""
ui_overlay.py
==============================================================
Interfaz 2D (HUD) que se dibuja ENCIMA de la escena 3D:
texto de zonas, panel de control, alertas, barra de estado.

Usamos pygame.font para generar texto como texturas y
OpenGL en modo ortográfico 2D para pintarlas sobre el 3D.
==============================================================
"""

import pygame
from OpenGL.GL import *
from OpenGL.GLU import *

# Colores (RGB 0-255)
CYAN = (0, 229, 255)
TEAL = (128, 203, 196)
WHITE = (224, 247, 250)
GREY = (84, 110, 122)
GREEN = (0, 230, 118)
ORANGE = (255, 152, 0)
RED = (244, 67, 54)
PURPLE = (124, 77, 255)
BG_PANEL = (13, 27, 42, 235)


class UIOverlay:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        pygame.font.init()
        self.font_small = pygame.font.SysFont("consolas", 13)
        self.font_med = pygame.font.SysFont("consolas", 16, bold=True)
        self.font_big = pygame.font.SysFont("consolas", 20, bold=True)
        self._tex_cache = {}

    def resize(self, w, h):
        self.width, self.height = w, h

    # ------------------------------------------------------------------
    def iniciar_modo_2d(self):
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        gluOrtho2D(0, self.width, self.height, 0)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_LIGHTING)

    def terminar_modo_2d(self):
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()

    # ------------------------------------------------------------------
    def _texto_a_textura(self, texto, font, color):
        key = (texto, id(font), color)
        if key in self._tex_cache:
            return self._tex_cache[key]
        surface = font.render(texto, True, color)
        data = pygame.image.tostring(surface, "RGBA", True)
        w, h = surface.get_size()
        tex_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, tex_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, data)
        self._tex_cache[key] = (tex_id, w, h)
        if len(self._tex_cache) > 400:   # evita crecer infinito
            self._tex_cache.clear()
        return tex_id, w, h

    def draw_text(self, texto, x, y, font=None, color=WHITE):
        font = font or self.font_small
        tex_id, w, h = self._texto_a_textura(texto, font, color)
        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, tex_id)
        glColor4f(1, 1, 1, 1)
        glBegin(GL_QUADS)
        glTexCoord2f(0, 1); glVertex2f(x, y)
        glTexCoord2f(1, 1); glVertex2f(x + w, y)
        glTexCoord2f(1, 0); glVertex2f(x + w, y + h)
        glTexCoord2f(0, 0); glVertex2f(x, y + h)
        glEnd()
        glDisable(GL_TEXTURE_2D)
        return w, h

    # ------------------------------------------------------------------
    def draw_rect(self, x, y, w, h, color, alpha=1.0):
        r, g, b = color[0]/255, color[1]/255, color[2]/255
        a = (color[3]/255 if len(color) > 3 else 1.0) * alpha
        glEnable(GL_BLEND)
        glColor4f(r, g, b, a)
        glBegin(GL_QUADS)
        glVertex2f(x, y)
        glVertex2f(x + w, y)
        glVertex2f(x + w, y + h)
        glVertex2f(x, y + h)
        glEnd()

    def draw_rect_border(self, x, y, w, h, color, thickness=1):
        r, g, b = color[0]/255, color[1]/255, color[2]/255
        glColor3f(r, g, b)
        glLineWidth(thickness)
        glBegin(GL_LINE_LOOP)
        glVertex2f(x, y)
        glVertex2f(x + w, y)
        glVertex2f(x + w, y + h)
        glVertex2f(x, y + h)
        glEnd()

    def draw_circle(self, cx, cy, radius, color, segments=16):
        r, g, b = color[0]/255, color[1]/255, color[2]/255
        glColor3f(r, g, b)
        glBegin(GL_TRIANGLE_FAN)
        glVertex2f(cx, cy)
        import math
        for i in range(segments + 1):
            ang = 2 * math.pi * i / segments
            glVertex2f(cx + radius * math.cos(ang), cy + radius * math.sin(ang))
        glEnd()

    # ------------------------------------------------------------------
    def draw_bar(self, x, y, w, h, pct, color_fill, color_bg=(10, 25, 41)):
        self.draw_rect(x, y, w, h, (*color_bg, 255))
        fill_w = max(0, min(w, w * pct / 100))
        self.draw_rect(x, y, fill_w, h, (*color_fill, 255))
