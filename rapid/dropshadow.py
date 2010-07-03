#!/usr/bin/python


import StringIO
import gtk
from PIL import Image, ImageFilter

def image_to_pixbuf(image):
    # this one handles transparency, unlike the default example in the pygtk FAQ
    # this is also from the pygtk FAQ
    IS_RGBA = image.mode=='RGBA'
    return gtk.gdk.pixbuf_new_from_data(
            image.tostring(), # data
            gtk.gdk.COLORSPACE_RGB, # color mode
            IS_RGBA, # has alpha
            8, # bits
            image.size[0], # width
            image.size[1], # height
            (IS_RGBA and 4 or 3) * image.size[0] # rowstride
            ) 
    

def image_to_pixbuf_no_transparency(image):
     fd = StringIO.StringIO()
     image.save(fd, "ppm")
     contents = fd.getvalue()
     fd.close()
     loader = gtk.gdk.PixbufLoader("pnm")
     loader.write(contents, len(contents))
     pixbuf = loader.get_pixbuf()
     loader.close()
     return pixbuf
     
def pixbuf_to_image(pb):
    assert(pb.get_colorspace() == gtk.gdk.COLORSPACE_RGB)
    dimensions = pb.get_width(), pb.get_height()
    stride = pb.get_rowstride()
    pixels = pb.get_pixels()
    mode = pb.get_has_alpha() and "RGBA" or "RGB"
    return Image.frombuffer(mode, dimensions, pixels,
                            "raw", mode, stride, 1)


class DropShadow():
    """
    Adds a gaussian blur drop shadow to a PIL image.
    
    Caches backgrounds of particular sizes for improved performance.
    
    Backgrounds can be made transparent.
    
    Modification of code from Kevin Schluff and Matimus
    License: Python license
    See:
    http://code.activestate.com/recipes/474116/ (r2)
    http://bytes.com/topic/python/answers/606952-pil-paste-image-top-other-dropshadow
    
    """
    
    def __init__(self, offset=(5,5), background_color=0xffffff, shadow = (0x44, 0x44, 0x44, 0xff), 
                                border=8, iterations=3, trim_border=False):
        """
        offset            - Offset of the shadow from the image as an (x,y) tuple. Can be
                            positive or negative.
        background_color  - Background colour behind the image.
        shadow            - Shadow colour (darkness).
        border            - Width of the border around the image. This must be wide
                            enough to account for the blurring of the shadow.
        trim_border       - If true, the border will only be created on the
                            sides it needs to be (i.e. only on two sides)
        iterations        - Number of times to apply the filter. More iterations 
                            produce a more blurred shadow, but increase processing time.
                                
        To make backgrounds transparent, ensure the alpha value of the shadow color is the 
        same as the background color, e.g. if background_color is 0xffffff, shadow's alpha should be 0xff
        """
        self.backgrounds = {}
        self.offset = offset
        self.background_color = background_color
        self.shadow = shadow
        self.border = border
        self.trim_border = trim_border
        self.iterations = iterations
        
        if self.offset[0] < 0 or not self.trim_border:
            self.left_spacing = self.border
        else:
            self.left_spacing = 0
        
        if self.offset[1] < 0 or not self.trim_border:
            self.top_spacing = self.border
        else:
            self.top_spacing = 0
        
        
    def dropShadow(self, image):
        """
        image             - The image to overlay on top of the shadow.
        """
        dimensions = (image.size[0], image.size[1])
        if not dimensions in self.backgrounds:
            
            # Create the backdrop image -- a box in the background colour with a 
            # shadow on it.
            
            if self.trim_border:
                totalWidth = image.size[0] + abs(self.offset[0]) + self.border
                totalHeight = image.size[1] + abs(self.offset[1]) + self.border
            else:
                totalWidth = image.size[0] + abs(self.offset[0]) + 2 * self.border
                totalHeight = image.size[1] + abs(self.offset[1]) + 2 * self.border
                
            back = Image.new("RGBA", (totalWidth, totalHeight), self.background_color)
            
            # Place the shadow, taking into account the offset from the image
            if self.offset[0] > 0 and self.trim_border:
                shadowLeft = max(self.offset[0], 0)
            else:
                shadowLeft = self.border + max(self.offset[0], 0)
            if self.offset[1] > 0 and self.trim_border:
                shadowTop = max(self.offset[1], 0)
            else:
                shadowTop = self.border + max(self.offset[1], 0)
            
            back.paste(self.shadow, [shadowLeft, shadowTop, shadowLeft + image.size[0], 
                shadowTop + image.size[1]] )
            
            # Apply the filter to blur the edges of the shadow.    Since a small kernel
            # is used, the filter must be applied repeatedly to get a decent blur.
            n = 0
            while n < self.iterations:
                back = back.filter(ImageFilter.BLUR)
                n += 1
                
            self.backgrounds[dimensions] = back
        
        # Paste the input image onto the shadow backdrop                
        imageLeft = self.left_spacing - min(self.offset[0], 0)
        imageTop = self.top_spacing - min(self.offset[1], 0)
            
        back = self.backgrounds[dimensions].copy()
        back.paste(image, (imageLeft, imageTop))
    
        return back
        

    
if __name__ == "__main__":
    import sys
    import os
    import common


    # create another file with a drop shadow
    f = sys.argv[1]
    
    image = Image.open(f)
    image.thumbnail((60,36), Image.ANTIALIAS)
    image2 = image.copy()
    
    path, name = os.path.split(f)
    name, ext = os.path.splitext(name)
     
    #image = dropShadow(image, shadow = (0x44, 0x44, 0x44, 0xff))
    dropShadow = DropShadow(offset=(3,3), shadow = (0x34, 0x34, 0x34, 0xff), border=6)
    image = dropShadow.dropShadow(image)
    image2 = dropShadow.dropShadow(image2)
    
    nf = os.path.join(path, "%s_small_shadow%s" % (name, ext))
    nf2 = os.path.join(path, "%s_small_shadow2%s" % (name, ext))
    image.save(nf)
    image2.save(nf2)
    print "wrote %s , %s" % (nf, nf2)
     
