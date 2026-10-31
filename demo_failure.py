#!/usr/bin/env python3
"""Standalone visual demo; it never contacts Bluetooth."""
from pathlib import Path
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk, Gdk, GLib
from neo_image import set_animation_frame

class Demo(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='dev.earbuds.NeoFailureDemo')

    def do_activate(self):
        window=Gtk.ApplicationWindow(application=self, title='Neo connection demo')
        window.set_default_size(400, 465); window.set_resizable(False); window.set_decorated(False)
        window.add_css_class('failure-window')
        css=Gtk.CssProvider()
        css.load_from_data(b'''
          window.failure-window { background: transparent; }
          .failure-card { background:#fff; border-radius:34px; color:#101010; }
          .failure-title { color:#101010; font-size:20px; font-weight:500; }
          .failure-close { min-width:30px; min-height:30px; padding:0; border-radius:99px; background:#f1f1f1; color:#888; border:0; box-shadow:none; font-size:22px; }
          .failure-retry { min-height:52px; border-radius:16px; border:0; box-shadow:none; background:#ededed; color:#303030; font-size:18px; }
          .failure-retry:hover { background:#e1e1e1; }
        ''')
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        card=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=0); card.add_css_class('failure-card')
        card.set_margin_top(4); card.set_margin_bottom(4); card.set_margin_start(4); card.set_margin_end(4); window.set_child(card)
        header=Gtk.CenterBox(); header.set_margin_top(22); header.set_margin_start(20); header.set_margin_end(20); card.append(header)
        spacer=Gtk.Box(); spacer.set_size_request(30,30); header.set_start_widget(spacer)
        title=Gtk.Label(label="Couldn't connect\nREDMI Headphones Neo"); title.add_css_class('failure-title')
        title.set_justify(Gtk.Justification.CENTER); title.set_wrap(True); header.set_center_widget(title)
        close=Gtk.Button(label='×'); close.add_css_class('failure-close'); close.set_tooltip_text('Close')
        close.set_valign(Gtk.Align.START); close.set_size_request(32,32)
        close.connect('clicked',lambda *_:window.close()); header.set_end_widget(close)
        picture=Gtk.Picture(); picture.set_can_shrink(True); picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        picture.set_size_request(280,240); picture.set_vexpand(True)
        card.append(picture)
        retry=Gtk.Button(label='Retry'); retry.add_css_class('failure-retry')
        retry.set_margin_start(32); retry.set_margin_end(32); retry.set_margin_bottom(30)
        retry.connect('clicked',lambda *_:title.set_text('Demo only\nNo connection attempted'))
        card.append(retry)
        window.present()
        index=[0]
        def advance():
            if not window.get_visible(): return GLib.SOURCE_REMOVE
            frame=Path(__file__).resolve().parent/'assets'/f'fc_01013D05_{4000+index[0]}.webp'
            set_animation_frame(picture, frame)
            index[0]+=1
            return GLib.SOURCE_REMOVE if index[0]>=75 else GLib.SOURCE_CONTINUE
        advance()
        GLib.timeout_add(34,advance)

if __name__=='__main__':
    raise SystemExit(Demo().run(None))
