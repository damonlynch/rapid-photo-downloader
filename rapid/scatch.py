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



        #~ pixbuf = self.props.pixbuf
        
        #~ image_w = pixbuf.get_width()
        #~ image_h = pixbuf.get_height()
        
        #~ format = cairo.FORMAT_RGB24
        #~ if pixbuf.get_has_alpha():
            #~ format = cairo.FORMAT_ARGB32
        #~ image = cairo.ImageSurface(format, image_w, image_h)
        
                #~ print image_w, image_h
                
                        

        
        name = os.path.basename(self.filename)
        name = os.path.join('/home/damon/tmp/rpd', name + '.jpg')
        #~ print name
        #~ self.image.save(name, 'jpeg')

        #~ imgd = self.image.tostring() #
        #~ imgd = self.image.tostring("raw","RGBA",0,1)


        #~ widget.style.paint_layout(window, gtk.STATE_NORMAL, True,
                                        #~ text_area, widget, self.filename,
                                        #~ x  + left_padding, text_y,
                                        #~ layout)
        
        #~ font_desc = pango.FontDescription("sans 8")
                                        
        #~ g = graphics.Graphics(cairo_context)
        #~ g.move_to(x, text_y)
        #~ g.set_color("#a9a9a9")
        #~ g.show_label(self.filename, 8, color="#a9a9a9")
        #~ g.show_text(self.filename)
        #~ g.show_layout(self.filename, font_desc, alignment=pango.ALIGN_CENTER)#, width=90) #, ellipsize=pango.ELLIPSIZE_END)
        
        #width=0, 
        
        

class DigitalFiles:
    """
    """

    
    def __init__(self, parent_app, builder):
        """
        """

        self.parent_app = parent_app
        
        self.preview_image = builder.get_object("preview_image")
        self.preview_image_aspectframe = builder.get_object("preview_image_aspectframe")
        
        self.selection_treeview = ThumbnailDisplay(self)
        
        selection_scrolledwindow = builder.get_object("selection_scrolledwindow")
        selection_scrolledwindow.add(self.selection_treeview)


        # Job code controls
        self.add_job_code_combo()
        left_pane_vbox = builder.get_object("left_pane_vbox")
        left_pane_vbox.pack_start(self.job_code_hbox, False, True)
                
        
        #Preview image
        self.base_preview_image = None # large size image used to scale down from
        self.current_preview_size = (0,0)
        
        self.preview_vpaned = builder.get_object("preview_vpaned")
        pos = self.parent_app.prefs.preview_vpaned_pos
        if pos == 0:
            pos = 300
        
        logger.info("Setting vertical pane to %s" % pos)
        self.preview_vpaned.set_position(pos)

        #leave room for thumbnail shadow
        if DROP_SHADOW:
            self.cacheDropShadow()
        else:
            self.shadow_size = 0
        
        image_size, shadow_size, offset = self._imageAndShadowSize()
        
        #~ self.preview_image.set_size_request(image_size, image_size)
        
        
        #Status of the file


        self.file_hpaned = builder.get_object("file_hpaned")
        if self.parent_app.prefs.hpaned_pos > 0:
            self.file_hpaned.set_position(self.parent_app.prefs.hpaned_pos)
        else:
            # this is what the user will see the first time they run the app
            self.file_hpaned.set_position(300)

        self.main_vpaned = builder.get_object("main_vpaned")
        self.main_vpaned.show_all()
        

    
    def set_display_preview_folders(self, value):
        if value and self.selection_treeview.previewed_file_treerowref:
            self.preview_destination_expander.show()
            self.preview_device_expander.show()

        else:
            self.preview_destination_expander.hide()
            self.preview_device_expander.hide()
            
    def cacheDropShadow(self):
        i, self.shadow_size, offset_v = self._imageAndShadowSize()
        self.drop_shadow = DropShadow(offset=(offset_v,offset_v), shadow = (0x44, 0x44, 0x44, 0xff), border=self.shadow_size, trim_border = True)
        
    def _imageAndShadowSize(self):
        #~ image_size = int(self.slider_adjustment.get_value())
        image_size = 500
        offset_v = max([image_size / 25, 5]) # realistically size the shadow based on the size of the image
        shadow_size = offset_v + 3
        image_size = image_size + offset_v * 2 + 3
        return (image_size, shadow_size, offset_v)
    
    def resize_image_callback(self, adjustment):
        """
        Resize the preview image after the adjustment value has been
        changed
        """
        size = int(adjustment.value)
        self.parent_app.prefs.preview_zoom = size
        self.cacheDropShadow()
        
        pixbuf = self.scaledPreviewImage()
        if pixbuf:
            self.preview_image.set_from_pixbuf(pixbuf)
            size = max([pixbuf.get_width(), pixbuf.get_height()])
            self.preview_image.set_size_request(size, size)
        else:    
            self.preview_image.set_size_request(size + self.shadow_size, size + self.shadow_size)

    def set_preview_image(self, pil_image):
        """
        """
        self.base_preview_image = pil_image
        self.resize_preview_image(overwrite=True)

        
    def resize_preview_image(self, max_width=None, max_height=None, overwrite=False):
        
        if max_width is not None and max_height is not None:
            logger.info("Max width and height set to %s, %s" % (max_width, max_height))
            self.preview_image_size_limit = (max_width, max_height)
        else:
            max_width, max_height = self.preview_image_size_limit
        
        if self.base_preview_image:
        
            base_image_width = self.base_preview_image.size[0]
            base_image_height = self.base_preview_image.size[1]
            
            logger.info("Base image: %s, %s" %(base_image_width, base_image_height))

            image_aspect = float(base_image_width) / base_image_height
            frame_aspect = float(max_width) / max_height
    

            # Frame is wider than image
            if frame_aspect > image_aspect:
                height = max_height
                width = int(height * image_aspect)
            # Frame is taller than image
            else:
                width = max_width
                height = int(width / image_aspect)
                
            logger.info("Will resize base image to width and height %s, %s" % (width, height))
    
            if width != self.current_preview_size[0] or height!= self.current_preview_size[1] or overwrite:
                
                pil_image = self.base_preview_image.copy()
                if base_image_width < width or base_image_height < height:
                    pil_image = tn.upsize_pil(pil_image, (width, height))
                else:
                    logger.info("Downsizing image")
                    tn.downsize_pil(pil_image, (width, height))
                    logger.info("Preview image size %s, %s" % (pil_image.size[0], pil_image.size[1]))
                    
                pixbuf = image_to_pixbuf(pil_image)
                self.preview_image.set_from_pixbuf(pixbuf)
                self.current_preview_size = (width, height)
        
        
    
    def set_job_code_display(self):
        """
        Shows or hides the job code entry
        
        If user is not using job codes in their file or subfolder names
        then do not prompt for it
        """

        if self.parent_app.needJobCodeForRenaming():
            self.job_code_hbox.show()
            self.job_code_label.show()
            self.job_code_combo.show()
            #~ self.selection_treeview.job_code_column.set_visible(True)
        else:
            self.job_code_hbox.hide()
            self.job_code_label.hide()
            self.job_code_combo.hide()
            #~ self.selection_treeview.job_code_column.set_visible(False)
    
    def update_job_code_combo(self):
        # delete existing rows
        while len(self.job_code_combo.get_model()) > 0:
            self.job_code_combo.remove_text(0)
        # add new ones
        for text in self.parent_app.prefs.job_codes:
            self.job_code_combo.append_text(text)
        # clear existing entry displayed in entry box
        self.job_code_entry.set_text('')
        
    
    def add_job_code_combo(self):
        self.job_code_hbox = gtk.HBox(spacing = 12)
        self.job_code_hbox.set_no_show_all(True)
        self.job_code_label = gtk.Label(_("Job Code:"))
        
        self.job_code_combo = gtk.combo_box_entry_new_text()
        for text in self.parent_app.prefs.job_codes:
            self.job_code_combo.append_text(text)
        
        # make entry box have entry completion
        self.job_code_entry = self.job_code_combo.child
        
        self.completion = gtk.EntryCompletion()
        self.completion.set_match_func(self.job_code_match_func)
        self.completion.connect("match-selected",
                             self.on_job_code_combo_completion_match)
        self.completion.set_model(self.job_code_combo.get_model())
        self.completion.set_text_column(0)
        self.job_code_entry.set_completion(self.completion)
        
        
        self.job_code_combo.connect('changed', self.on_job_code_resp)
        
        self.job_code_entry.connect('activate', self.on_job_code_entry_resp)
        
        self.job_code_combo.set_tooltip_text(_("Enter a new Job Code and press Enter, or select an existing Job Code"))

        #add widgets
        self.job_code_hbox.pack_start(self.job_code_label, False, False)
        self.job_code_hbox.pack_start(self.job_code_combo, True, True)
        self.set_job_code_display()

    def job_code_match_func(self, completion, key, iter):
         model = completion.get_model()
         return model[iter][0].lower().startswith(self.job_code_entry.get_text().lower())
         
    def on_job_code_combo_completion_match(self, completion, model, iter):
         self.job_code_entry.set_text(model[iter][0])
         self.job_code_entry.set_position(-1)
         
    def on_job_code_resp(self, widget):
        """
        When the user has clicked on an existing job code
        """
        
        # ignore changes because the user is typing in a new value
        if widget.get_active() >= 0:
            self.job_code_chosen(widget.get_active_text())
            
    def on_job_code_entry_resp(self, widget):
        """
        When the user has hit enter after entering a new job code
        """
        self.job_code_chosen(widget.get_text())
        
    def job_code_chosen(self, job_code):
        """
        The user has selected a Job code, apply it to selected images. 
        """
        self.selection_treeview.apply_job_code(job_code, overwrite = True)
        self.completion.set_model(None)
        self.parent_app.assignJobCode(job_code)
        self.completion.set_model(self.job_code_combo.get_model())
            
    def add_file(self, rpd_file):
        self.selection_treeview.add_file(rpd_file)

