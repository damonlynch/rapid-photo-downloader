#!/usr/bin/python
# -*- coding: latin1 -*-

### Copyright (C) 2011-2012 Damon Lynch <damonlynch@gmail.com>

### This program is free software; you can redistribute it and/or modify
### it under the terms of the GNU General Public License as published by
### the Free Software Foundation; either version 2 of the License, or
### (at your option) any later version.

### This program is distributed in the hope that it will be useful,
### but WITHOUT ANY WARRANTY; without even the implied warranty of
### MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
### GNU General Public License for more details.

### You should have received a copy of the GNU General Public License
### along with this program; if not, write to the Free Software
### Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301
### USA

import subprocess
import os

import multiprocessing, logging
logger = multiprocessing.get_logger()

from optparse import OptionParser

import pyexiv2

# Copyright, Description, Creator and Date/Time are found in Exif, IPTC-IIM and XMP
# XMP and Exif: "When the file format supports both Exif and XMP, a Changer SHOULD update both forms of a value."

"""Exif date/time values such as DateTimeOriginal do not contain time zone information. The camera is
presumably in an appropriate local time when a photograph is taken, but there is no indication in the
Exif metadata of what that time zone was. The photograph's time zone MUST NOT be presumed to be
the same as that of a computer later used to process the photograph."""

"""The XMP specification formats date/time values according to the Date and Time (W3C) document. In
this standard, a time zone designator is required if any time information is present. A date-only value is
allowed. The XMP specification has been recently revised to make the time zone designator be
optional."""

"""A Changer MUST NOT implicitly add a time zone when editing values. It is okay to be
explicit about time zones if desired."""

#Exif ImageDescription
#XMP (dc:description[“x-default”])

#Exif DateTime (306, 0x132) and SubSecTime (37520, 0x9290)
#XMP (xmp:ModifyDate)
#Exif DateTime is mapped to XMP (xmp:ModifyDate). Any change to the file SHOULD cause both to be
#updated.

#Exif Copyright
#XMP (dc:rights).
#CopyrightURL SHOULD be stored in XMP (xmpRights:WebStatement)

#Exif Artist
#XMP (dc:creator)
#The semicolon-space separator suggested by Exif SHOULD be recognized when mapping between
#the single TIFF Artist string and the individual array items in IIM By-line and XMP (dc:creator).

#Iptc4xmpExt:LocationCreated, a structure using the IPTC type LocationDetails.
#Iptc4xmpExt:LocationShown, an unordered array of structures using the IPTC type LocationDetails.


"""The IPTC Extension specification introduced a mechanism that clearly defines the difference between
where an image has been taken Location Created and where the content being shown on the image is
located Location Shown."""





def not_proprietary_raw(ext):
    """Returns True if the file is not a proprietary RAW file 
    e.g. if it is jpeg, tiff or DNG
    
    Checks using file extension only."""
    return ext in ['jpg', 'jpeg', 'tif', 'tiff', 'dng']


default_blank_xmp_template = """<?xml version="1.0" encoding="UTF-8"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="XMP Core 4.4.0-Exiv2">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
 </rdf:RDF>
</x:xmpmeta>"""



class Pyexiv2XmpMetadata(pyexiv2.ImageMetadata):
    """
    Adds support for reading and writing XMP sidecar files to pyexiv2 0.3.x
    
    New variables:
    self.xmp_sidecar_filename
    self.xmp_sidecar
    """
    
    def __init__(self, filename, blank_xmp_template=None):
        pyexiv2.ImageMetadata.__init__(self, filename)
        
        self.xmp_sidecar_filename = None
        self.xmp_sidecar = None
        if blank_xmp_template is None:
            self.blank_xmp_template = default_blank_xmp_template
        else:
            self.blank_xmp_template = blank_xmp_template
        
        name, ext = os.path.splitext(filename)
        self.__dfl_name = name
        self.__dfl_ext = ext[1:].lower()
        
    def read(self):
        pyexiv2.ImageMetadata.read(self)
        
        #If XMP sidecar exists, read it
        self.xmp_sidecar_filename = self.has_xmp_sidecar()
        if self.xmp_sidecar_filename:
            self.read_xmp_sidecar()
                
    
    def _generate_xmp_sidecar_filename(self):
        return self.__dfl_name + '.xmp'
    
    def has_xmp_sidecar(self):
        """Checks the file system for the presence of XMP sidecar.
        Assumes lower case file extension.
        
        Returns file name of xmp sidecar, if it exists, else returns None."""
        
        xmp_sidecar_filename = self._generate_xmp_sidecar_filename()
        if os.path.exists(xmp_sidecar_filename):
            if os.path.isfile(xmp_sidecar_filename):
                return xmp_sidecar_filename
        return None
                
    def read_xmp_sidecar(self):
        """
        Reads metadata from xmp side car file
        """
        self.xmp_sidecar = pyexiv2.ImageMetadata(self.xmp_sidecar_filename)
        self.xmp_sidecar.read()
        
    def _copy_xmp(self, source, dest, overwrite):
        print "dest keys %s" % dest.xmp_keys
        if overwrite:
            for xmp_key in source.xmp_keys:
                tag = source[xmp_key]
                dest[xmp_key] = pyexiv2.XmpTag(xmp_key,tag.value)
                print "Copied %s %s" % (xmp_key, source[xmp_key].value)

        else:
            for xmp_key in source.xmp_keys:
                if not xmp_key in dest.xmp_keys:
                    tag = source[xmp_key]
                    dest[xmp_key] = pyexiv2.XmpTag(xmp_key,tag.value)
                else:
                    print "Already have %s" % xmp_key
    
    
    def merge_from_xmp_sidecar(self, overwrite=False):
        """
        Takes metadata from sidecar and inserts it into metadata for image. 
        
        If overwrite is True, then any existing values in the image are overwritten.
        """
        self._copy_xmp(self.xmp_sidecar, self, overwrite)

    def merge_to_xmp_sidecar(self, overwrite=True):
        """
        Takes metadata from image and inserts it sidecar. 
        
        If overwrite is True, then any existing values in the image are overwritten.
        """        
        for xmp_key in self.xmp_keys:
            tag = self[xmp_key]
            self.xmp_sidecar[xmp_key] = pyexiv2.XmpTag(xmp_key, tag.value)
            print "Copied %s %s" % (xmp_key, self[xmp_key].value)
        
        
    def write(self):
        """
        If image is not a proprietary RAW file (i.e. jpeg, tiff, or DNG),
        then write to original image.
        
        Else write to XMP sidecar file.
        If sidecar already exists, then attempt to merge data.
        """
        if self.not_proprietary_raw():
            pyexiv2.ImageMetadata.write(self)
        else:
            if self.xmp_sidecar_filename is None:
                # There is a very slim chance an XMP sidecar may have been
                # created after the read() operation was issued. If so, read it
                self.xmp_sidecar_filename = self.has_xmp_sidecar()
                if self.xmp_sidecar_filename:
                    self.read_xmp_sidecar()
                else:
                    # create XMP file
                    self.xmp_sidecar_filename = self._generate_xmp_sidecar_filename()
                    f = open(self.xmp_sidecar_filename, 'w')
                    f.write(self.blank_xmp_template)
                    f.close()
                    self.read_xmp_sidecar()
             
            print ".. Merging from sidecar"
            self.merge_from_xmp_sidecar(overwrite=False)
            print ".. Merging TO sidecar"
            self.merge_to_xmp_sidecar(overwrite=True)
            self.xmp_sidecar.write()

                
    def not_proprietary_raw(self):
        """Returns True if the file is not a proprietary RAW file 
        e.g. if it is jpeg, tiff or DNG """
        return not_proprietary_raw(self.__dfl_ext)

class Exiv2XmpMetadataSidecar:
    
    def __init__(self, filename):
        self.filename = filename
        self.keys = []
    
    def _add_pair(self, key_value_pair):
        self.keys.append(key_value_pair)
        logger.debug(key_value_pair)
        
    def _generate_exiv2_command_line(self):
        # -f option: overwrites any existing xmp file
        return ['exiv2', '-f'] + self.keys + ['-exX', self.filename]
    
    def _generate_exiv2_contact_info(self, key, value):
        return "-M set Xmp.iptc.CreatorContactInfo/Iptc4xmpCore:%s %s" % (key, value)
        
    def _generate_exiv2_dc(self, key, value):
        return "-M set Xmp.dc.%s %s" % (key, value)
    
    def _generate_exiv2_photoshop(self, key, value):
        return "-M set Xmp.photoshop.%s %s" % (key, value)
        
    def _generate_exiv2_rights(self, key, value):
        return "-M set Xmp.xmpRights.%s %s" % (key, value)
        
    def _generate_exiv2_iptc(self, key, value):
        return "-M set Xmp.iptc.%s %s" % (key, value)
        
    def _generate_exiv2_iptc_ext(self, key, value):
        return "-M set Xmp.iptcExt.%s %s" % (key, value)
        
    def _generate_exiv2_exif(self, key, value):
        return "-M set Xmp.exif.%s %s" % (key, value)
        
    def set_iptc_ext_sublocation(self, sublocation):
        self._add_pair(self._generate_exiv2_iptc_ext('Sublocation', sublocation))
    
    def set_location(self, location):
        self._add_pair(self._generate_exiv2_iptc('Location', location))
        
    def set_iptc_ext_location_created(self, location):
        self._add_pair(self._generate_exiv2_iptc_ext('LocationCreated', location))
        
    def set_iptc_ext_location_shown(self, location):
        self._add_pair(self._generate_exiv2_iptc_ext('LocationShown', location))        
    
    def set_city(self, city):
        self._add_pair(self._generate_exiv2_photoshop('City', city))
        
    def set_iptc_ext_city(self, city):
        self._add_pair(self._generate_exiv2_iptc_ext('City', location))
        
    def set_state_province(self, state):
        self._add_pair(self._generate_exiv2_photoshop('State', state))
        
    def set_iptc_ext_state_province(self, state):
         self._add_pair(self._generate_exiv2_iptc_ext('ProvinceState', state))
        
    def set_country(self, country):
        self._add_pair(self._generate_exiv2_photoshop('Country', country))
        
    def set_iptc_ext_country(self, country):
        self._add_pair(self._generate_exiv2_iptc('CountryName', country))
        
    def set_country_code(self, country_code):
        self._add_pair(self._generate_exiv2_iptc('CountryCode', country_code))
        
    def set_iptc_ext_country_code(self, country_code):
        self._add_pair(self._generate_exiv2_iptc_ext('CountryCode', country_code))
        
    def set_iptc_ext_world_region(self, world_region):
        self._add_pair(self._generate_exiv2_iptc_ext('WorldRegion', world_region))
    
    def set_headline(self, headline):
        self._add_pair(self._generate_exiv2_photoshop('Headline', headline))
        
    def set_description_writer(self, writer):
        """
        Synonym: Caption writer
        """
        self._add_pair(self._generate_exiv2_photoshop('CaptionWriter', writer))
        
    def set_description(self, description):
        """A synonym for this in some older programs is 'Caption'"""
        self._add_pair(self._generate_exiv2_dc('description', description))
        
    def set_subject(self, subject):
        """
        You can call this more than once, to add multiple subjects
        
        A synonym is 'Keywords'
        """
        self._add_pair(self._generate_exiv2_dc('subject', subject))
        
    def set_person_in_image(self, person):
        self._add_pair(self._generate_exiv2_iptc_ext('PersonInImage', person))
        
    def set_creator(self, creator):
        """
        Sets the author (creator) field. Photo Mechanic calls this 'Photographer'.
        """
        self._add_pair(self._generate_exiv2_dc('creator', creator))
        
    def set_creator_job_title(self, job_title):
        self._add_pair(self._generate_exiv2_photoshop('AuthorsPosition', job_title))
        
    def set_credit_line(self, credit_line):
        self._add_pair(self._generate_exiv2_photoshop('Credit', credit_line))
        
    def set_source(self, source):
        """
        original owner or copyright holder of the photograph
        """
        self._add_pair(self._generate_exiv2_photoshop('Source', source))
    
    def set_copyright(self, copyright):
        self._add_pair(self._generate_exiv2_dc('rights', copyright))
        
    def set_copyright_url(self, copyright_url):
        self._add_pair(self._generate_exiv2_rights('WebStatement', copyright_url))
    
    def set_contact_city(self, city):
        self._add_pair(self._generate_exiv2_contact_info('CiAdrCity', city))
        
    def set_contact_country(self, country):
        self._add_pair(self._generate_exiv2_contact_info('CiAdrCtry', country))
        
    def set_contact_address(self, address):
        """The contact information address part.
        Comprises an optional company name and all required information 
        to locate the building or postbox to which mail should be sent."""
        self._add_pair(self._generate_exiv2_contact_info('CiAdrExtadr', address))
        
    def set_contact_postal_code(self, postal_code):
        self._add_pair(self._generate_exiv2_contact_info('CiAdrPcode', postal_code))

    def set_contact_region(self, region):
        """State/Province"""
        self._add_pair(self._generate_exiv2_contact_info('CiAdrRegion', region))
        
    def set_contact_email(self, email):
        """Multiple email addresses can be given, separated by a comma."""
        self._add_pair(self._generate_exiv2_contact_info('CiEmailWork', email))
        
    def set_contact_telephone(self, telephone):
        """Multiple numbers can be given, separated by a comma."""
        self._add_pair(self._generate_exiv2_contact_info('CiTelWork', telephone))
        
    def set_contact_url(self, url):
        """Multiple URLs can be given, separated by a comma."""
        self._add_pair(self._generate_exiv2_contact_info('CiUrlWork', url))
        
    def set_exif_value(self, key, value):
        self._add_pair(self._generate_exiv2_exif(key, value))
        
    def write_xmp_sidecar(self):
        cmd = self._generate_exiv2_command_line()
        if logger.getEffectiveLevel() == logging.DEBUG:
            cmd_line = ''
            for c in cmd:
                cmd_line += c + ' '
            cmd_line = cmd_line.strip()
            logger.debug("XMP write command: %s", cmd_line)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        return proc.communicate()[0].strip()
        

if __name__ == '__main__':
    
    parser = OptionParser()
    parser.set_defaults(exiv2=False)
    parser.add_option("-e",  "--exiv2",  action="store_true", dest="exiv2",  help=("create sample XMP sidecar file using exiv2  (default: %default)"))
    (options, args) = parser.parse_args()
    
    if not args:
        print 'please suppply path/to/photo/containing/metadata'
        
    else:
        f = args[0]
        if options.exiv2:
            x = Exiv2XmpMetadataSidecar(f)
            x.set_description("This is image is just a sample and is nothing serious. I used to test out writing XMP files in Rapid Photo Downloader.")
            x.set_description_writer("Damon Lynch wrote caption")
            x.set_headline("Sample image to test XMP")
            x.set_subject("Keyword 1")
            x.set_subject("Keyword 2")
            x.set_city("Minneapolis")
            x.set_location("University of Minnesota")
            x.set_state_province("Minnesota")
            x.set_country("United States of America")
            x.set_country_code("USA")
            x.set_creator("Damon Lynch")
            x.set_creator_job_title("Photographer")
            x.set_credit_line("Contact Damon for permission")
            x.set_source("Damon Lynch is the original photographer")
            x.set_copyright("© 2011 Damon Lynch, all rights reserved.")
            x.set_copyright_url("http://www.damonlynch.net/license")
            # pyexiv2 0.3.2 fails with these next values:
            x.set_contact_address("Contact house number, street, apartment")
            x.set_contact_city('Contact City')
            x.set_contact_region('Contact State')
            x.set_contact_postal_code('Contact Post code')
            x.set_contact_telephone('+1 111 111 1111')
            x.set_contact_country('Contact Country')
            x.set_contact_address('Address\nApartment')
            x.set_contact_url('http://www.sample.net')
            x.set_contact_email('name@email1.com, name@email2.com')
            
            x.write_xmp_sidecar()
        else:
            x = Pyexiv2XmpMetadata(f)
            x.read()
            print "XMP keys from image only:"
            print x.xmp_keys
            
            if not x.has_xmp_sidecar():
                print "No XMP sidecar detected - creating XMP test data...."
                key = 'Xmp.dc.description'
                x[key] = pyexiv2.XmpTag(key,u"Description created using pyexiv2")
                print "Updating image or creating sidecar"
                x.write()
                print "wrote to file"
            else:
                print "XMP keys from sidecar:"
                print x.xmp_sidecar.xmp_keys
                print "Creating new value in image"
                key = 'Xmp.dc.description'
                x[key] = pyexiv2.XmpTag(key,u"Description UPDATED using pyexiv2")
                key2 = 'Xmp.photoshop.Country' 
                x[key2] = pyexiv2.XmpTag(key2, u"Kiwi")
                #~ print "Merging from sidecar to image...."
                #~ x.merge_from_xmp_sidecar()
                print "New image keys:"
                print x.xmp_keys
                print "Updating image or sidecar"
                x.write()
                #~ if x.xmp_sidecar:
                print x.xmp_sidecar[key].value
                print x.xmp_sidecar[key2].value
                print "wrote to file"
            x = None
