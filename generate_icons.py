#!/usr/bin/env python3
"""
Icon generator for ClockWise.
Renders the C-Wing logo into high-resolution PNGs (16, 24, 32, 48, 256 px) and .ico.
Adheres to ClockWise Design Bible:
- Symbol alone for tray and window icons
- 16, 24, 32, 48, and 256 px
- Coral on transparent / teal background
"""
import os
from PIL import Image, ImageDraw

def cubic_bezier(p0, p1, p2, p3, n=30):
    points = []
    for i in range(n + 1):
        t = i / n
        u = 1.0 - t
        x = (u**3 * p0[0] +
             3 * u**2 * t * p1[0] +
             3 * u * t**2 * p2[0] +
             t**3 * p3[0])
        y = (u**3 * p0[1] +
             3 * u**2 * t * p1[1] +
             3 * u * t**2 * p2[1] +
             t**3 * p3[1])
        points.append((x, y))
    return points

def get_c_wing_polygon(scale=1.0, offset_x=0.0, offset_y=0.0):
    # Normalized coordinates around 200x200 canvas
    # Path segments matching SVG:
    # M 172,42
    # C 135,36 68,58 42,106
    # C 24,142 42,182 86,188
    # C 116,192 146,186 170,170
    # L 155,148
    # C 136,160 116,164 96,162
    # C 68,158 58,134 62,112
    # C 68,88 92,72 122,72
    # C 138,72 154,78 168,88
    # C 156,76 148,68 152,62
    # C 158,54 166,48 172,42
    cmds = [
        ('M', (172, 42)),
        ('C', (135, 36), (68, 58), (42, 106)),
        ('C', (24, 142), (42, 182), (86, 188)),
        ('C', (116, 192), (146, 186), (170, 170)),
        ('L', (155, 148)),
        ('C', (136, 160), (116, 164), (96, 162)),
        ('C', (68, 158), (58, 134), (62, 112)),
        ('C', (68, 88), (92, 72), (122, 72)),
        ('C', (138, 72), (154, 78), (168, 88)),
        ('C', (156, 76), (148, 68), (152, 62)),
        ('C', (158, 54), (166, 48), (172, 42))
    ]
    
    poly = []
    curr = cmds[0][1]
    poly.append(curr)
    
    for cmd in cmds[1:]:
        if cmd[0] == 'C':
            pts = cubic_bezier(curr, cmd[1], cmd[2], cmd[3], n=24)
            poly.extend(pts[1:])
            curr = cmd[3]
        elif cmd[0] == 'L':
            poly.append(cmd[1])
            curr = cmd[1]

    # Center and scale
    scaled_poly = []
    for x, y in poly:
        sx = (x - 100) * scale + 100 + offset_x
        sy = (y - 100) * scale + 100 + offset_y
        scaled_poly.append((sx, sy))
        
    return scaled_poly

def render_logo(size, color=(231, 91, 60), bg_color=None):
    # Render with 4x supersampling for ultra smooth antialiasing
    super_size = size * 4
    scale = (super_size / 200.0) * 0.92
    
    img = Image.new('RGBA', (super_size, super_size), bg_color or (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Scale points
    poly = get_c_wing_polygon(scale=1.0, offset_x=0, offset_y=0)
    super_poly = [((x * super_size / 200.0), (y * super_size / 200.0)) for x, y in poly]
    
    draw.polygon(super_poly, fill=color)
    
    # Downsample using high-quality Lanczos filter
    final_img = img.resize((size, size), Image.Resampling.LANCZOS)
    return final_img

def generate_all_icons(output_dir='icons'):
    os.makedirs(output_dir, exist_ok=True)
    coral = (231, 91, 60, 255)
    teal = (16, 60, 58, 255)
    off_white = (243, 238, 231, 255)
    
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images_for_ico = []
    
    for sz in sizes:
        # Transparent coral
        img_coral = render_logo(sz, color=coral)
        img_coral.save(os.path.join(output_dir, f'logo_coral_{sz}.png'))
        
        # Teal version (for day mode on off-white)
        img_teal = render_logo(sz, color=teal)
        img_teal.save(os.path.join(output_dir, f'logo_teal_{sz}.png'))

        # Off-white version (for night mode on deep teal)
        img_white = render_logo(sz, color=off_white)
        img_white.save(os.path.join(output_dir, f'logo_white_{sz}.png'))
        
        if sz in [16, 24, 32, 48, 256]:
            images_for_ico.append(img_coral)
            
    # Save .ico containing standard Windows icon resolutions
    ico_path = os.path.join(output_dir, 'clockwise.ico')
    # Use 256 as base, append others
    images_for_ico[-1].save(
        ico_path,
        format='ICO',
        sizes=[(s.width, s.height) for s in images_for_ico]
    )
    print(f"Generated icons in {output_dir}/ including {ico_path}")

if __name__ == '__main__':
    generate_all_icons()
