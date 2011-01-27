class PicklablePixBuf:
    """
    A convenience class to allow Pixbufs to be passed between processes.
    
    THIS DOES NOT SEEM TO WORK! IMAGES BECOME CORRUPTED AND THERE ARE MEMORY LEAKS
    
    Pixbufs cannot be pickled, which means they cannot be exchanged between
    processes. This class converts them into a numeric array that can be
    pickled.
    
    Source for background information:
    http://lisas.de/~alex/?p=46
    https://bugzilla.gnome.org/show_bug.cgi?id=309469
    """
    def __init__(self, pixbuf):
        """Pixbuf to be pickled"""
        self.array = pixbuf.get_pixels_array()
        self.colorspace = pixbuf.get_colorspace()
        self.bits_per_sample = pixbuf.get_bits_per_sample()
        self.md5 = hashlib.md5(self.array).hexdigest()
        
    def get_pixbuf(self):
        """Return the pixbuf"""
        assert self.md5 == hashlib.md5(self.array).hexdigest()

        return gtk.gdk.pixbuf_new_from_array(self.array, 
                                             self.colorspace,
                                             self.bits_per_sample)
                                             
class PhotoThumbnail_v1:
    """
    Class for using pyexiv2 0.1.x
    Not complete
    needs to be converted to PIL
    """
    def __init__(self):
        pass
        
            
    def get_thumbnail(self, full_file_name, size):
        thumbnail = None
        thumbnail_icon = None        
        metadata = pyexiv2.Image(full_file_name)
        try:
            metadata.readMetadata()
        except:
            logger.warning("Could not read metadata from %s" % full_file_name)
        else:
            thumbnail_type, thumbnail_data = metadata.getThumbnailData()
            if isinstance(thumbnail_data, types.StringType):
                orientation = metadata['Exif.Image.Orientation']
                pbloader = gtk.gdk.PixbufLoader()
                pbloader.write(thumbnail_data)
                pbloader.close()
                # Get the resulting pixbuf and build an image to be displayed
                pixbuf = pbloader.get_pixbuf()
                if orientation == 8:
                    pixbuf = pixbuf.rotate_simple(gtk.gdk.PIXBUF_ROTATE_COUNTERCLOCKWISE)
                elif orientation == 6:
                    pixbuf = pixbuf.rotate_simple(gtk.gdk.PIXBUF_ROTATE_CLOCKWISE)
                elif orientation == 3:
                    pixbuf = pixbuf.rotate_simple(gtk.gdk.PIXBUF_ROTATE_UPSIDEDOWN)
                thumbnail_icon = PicklablePixBuf(
                                        common.scale2pixbuf(60, 36, pixbuf))                
                thumbnail = PicklablePixBuf(pixbuf)

        return (thumbnail, thumbnail_icon)                                             
