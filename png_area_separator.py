import cv2
import numpy as np

# 1. Load and build a binary mask (255 = shape)
img = cv2.imread("shape.png", cv2.IMREAD_UNCHANGED)
if img.ndim == 3 and img.shape[2] == 4:            # PNG with transparency
    mask = (img[:, :, 3] > 127).astype(np.uint8) * 255
    out = img.copy()
else:                                              # black shape on white
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)
    out = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)

# 2. Label every separate blob once (0 = background)
n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
print(f"{n - 1} regions found")

# 3. "Click" on a pixel -> region id
x, y = 300, 350
rid = labels[y, x]                                 # 0 means you clicked the background

if rid != 0:
    region = (labels == rid)                       # boolean mask of that region

    # 4a. Change color (keeps alpha channel)
    out[region, :3] = (0, 0, 255)                  # BGR red

    # 4b. Add a border: dilate the mask, subtract the original
    r8 = region.astype(np.uint8)
    ring = cv2.dilate(r8, np.ones((9, 9), np.uint8)) - r8
    out[ring > 0] = (255, 200, 0, 255)             # BGRA border color

    # 4c. Fill with another image
    fill = cv2.imread("texture.png")
    bx, by, bw, bh, _ = stats[rid]                 # bounding box of the region
    fill = cv2.resize(fill, (bw, bh))
    sub = region[by:by+bh, bx:bx+bw]
    out[by:by+bh, bx:bx+bw, :3][sub] = fill[sub]

cv2.imwrite("result.png", out)