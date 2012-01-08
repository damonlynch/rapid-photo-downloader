#!/usr/bin/python
# -*- coding: latin1 -*-

### Copyright (C) 2011-12 Damon Lynch <damonlynch@gmail.com>

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
### Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

import subprocess

import multiprocessing, logging
logger = multiprocessing.get_logger()

class XmpMetadataSidecar:
    
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
        
    def _generate_exiv2_exif(self, key, value):
        return "-M set Xmp.exif.%s %s" % (key, value)
        
    def set_location(self, location):
        self._add_pair(self._generate_exiv2_iptc('Location', location))
    
    def set_city(self, city):
        self._add_pair(self._generate_exiv2_photoshop('City', city))
        
    def set_state_province(self, state):
        self._add_pair(self._generate_exiv2_photoshop('State', state))
        
    def set_country(self, country):
        self._add_pair(self._generate_exiv2_photoshop('Country', country))
        
    def set_country_code(self, country_code):
        self._add_pair(self._generate_exiv2_iptc('CountryCode', country_code))
    
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
    import sys
    
    
    if (len(sys.argv) != 2):
        print 'Usage: ' + sys.argv[0] + ' path/to/photo/containing/metadata'
        
    else:
        x = XmpMetadataSidecar(sys.argv[1])
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
