# Coatrun

This software is a fork of Printrun 2.0, heavily slimmed down and optimized to control a dispensing robot for selective conformal coating of printed circuit boards. The state of the project is currently non-functional under development. It is planned to implement vision using OpenCV to locate fiducial marks on the PCB surface. The user interface has been optimized for touchscreen usage.

Fedora is (and will be) the only actively supported host system. OS-specific code was not removed from Coatrun, so it may run with all operating systems supported by Printrun.

I don't expect this to become a popular project, I develope this solely for my own needs. If you plan to build a dispensing robot feel free to contact me!

## CONTRIBUTORS

An enormous number of people helped make Printrun. See the list
[here](CONTRIBUTORS.md).

## Dependencies

To use coaterface, you need:

  * Python 3 (ideally 3.10),
  * pyserial (or python3-serial on ubuntu/debian)
  * pyreadline (not needed on Linux)
  * wxPython 4
  * pyglet
  * appdirs
  * numpy (for 3D view)
  * pycairo (to use Projector feature)
  * cairosvg (to use Projector feature)
  * dbus (to inhibit sleep on some Linux systems)

## LICENSE

```
Copyright (C) 2011-2022 Kliment Yanev, Guillaume Seguin, and the other contributors listed in CONTRIBUTORS.md

Printrun is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Printrun is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Printrun.  If not, see <http://www.gnu.org/licenses/>.
```

All scripts should contain this license note, if not, feel free to ask us. Please note that files where it is difficult to state this license note (such as images) are distributed under the same terms.
