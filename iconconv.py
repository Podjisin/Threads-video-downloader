from PIL import Image

img = Image.open("icon_cropped.png").convert("RGBA")
img.save(
    "icon.ico",
    sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)]
)
