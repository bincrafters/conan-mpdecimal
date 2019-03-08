#!/usr/bin/env python
# -*- coding: utf-8 -*-

from conans import ConanFile, AutoToolsBuildEnvironment, tools
from conans.errors import ConanException, ConanInvalidConfiguration
from conans.util.env_reader import get_env
import os
import shutil
import tempfile


class MpdecimalConan(ConanFile):
    name = "mpdecimal"
    version = "2.4.2"
    description = "mpdecimal is a package for correctly-rounded arbitrary precision decimal floating point arithmetic."
    license = "BSD-2-Clause"
    topics = ("conan", "mpdecimal", "multiprecision", "library")
    url = "https://github.com/bincrafters/conan-mpdecimal"
    homepage = "http://www.bytereef.org/mpdecimal"
    author = "Bincrafters <bincrafters@gmail.com>"

    settings = "os", "compiler", "build_type", "arch"
    options = {
        "shared": [True, False],
        "fPIC": [True, False],
    }
    default_options = {
        "shared": False,
        "fPIC": True,
    }

    _source_subfolder = "sources"

    def configure(self):
        if self.settings.arch not in ("x86", "x86_64"):
            raise ConanInvalidConfiguration("Arch is unsupported")
        del self.settings.compiler.libcxx

    def config_options(self):
        if self.options.shared or self.settings.compiler == "Visual Studio":
            del self.options.fPIC

    def build_requirements(self):
        if self.settings.os == "Windows" and self.settings.compiler != "Visual Studio":
            self.build_requires("msys2_installer/latest@bincrafters/stable")

    def source(self):
        filename = "{}-{}.tar.gz".format(self.name, self.version)
        url = "http://www.bytereef.org/software/mpdecimal/releases/{}".format(filename)
        sha256 = "83c628b90f009470981cf084c5418329c88b19835d8af3691b930afccb7d79c7"

        dlfilepath = os.path.join(tempfile.gettempdir(), filename)
        if os.path.exists(dlfilepath) and not get_env("MPDECIMAL_FORCE_DOWNLOAD", False):
            self.output.info("Skipping download. Using cached {}".format(dlfilepath))
        else:
            self.output.info("Downloading {} from {}".format(filename, url))
            tools.download(url, dlfilepath)
        tools.check_sha256(dlfilepath, sha256)
        tools.untargz(dlfilepath)
        os.rename("{}-{}".format(self.name, self.version), self._source_subfolder)

    def build(self):
        if self.source_folder != self.build_folder:
            self.output.info("Copying source tree to build folder...")
            shutil.rmtree(os.path.join(self.build_folder, self._source_subfolder), ignore_errors=True)
            shutil.copytree(os.path.join(self.source_folder, self._source_subfolder), os.path.join(self.build_folder, self._source_subfolder))
        if self.settings.compiler == "Visual Studio":
            self._build_msvc()
        else:
            self._build_autotools()

    def _build_msvc(self):
        arch_ext = "{}".format(32 if self.settings.arch == "x86" else 64)
        vcbuild_folder = os.path.join(self.build_folder, self._source_subfolder, "vcbuild")

        libmpdec_folder = os.path.join(self.build_folder, self._source_subfolder, "libmpdec")

        dist_folder = os.path.join(vcbuild_folder, "dist{}".format(arch_ext))
        os.mkdir(dist_folder)

        makefile_vc_original = os.path.join(libmpdec_folder, "Makefile.vc")
        for msvcrt in ("MDd", "MTd", "MD", "MT"):
            tools.replace_in_file(makefile_vc_original,
                                  msvcrt,
                                  str(self.settings.compiler.runtime))

        shutil.copy(os.path.join(libmpdec_folder, "Makefile.vc"), os.path.join(libmpdec_folder, "Makefile"))
        with tools.chdir(libmpdec_folder):
            with tools.environment_append(tools.vcvars_dict(self.settings)):
                self.run("nmake clean")
                self.run("nmake MACHINE={machine} DLL={dll}".format(
                    machine="ppro" if self.settings.arch == "x86" else "x64",
                    dll="1" if self.options.shared else "0"))

            shutil.copy("mpdecimal.h", dist_folder)
            if self.options.shared:
                shutil.copy("libmpdec-{}.dll".format(self.version), os.path.join(dist_folder, "libmpdec-{}.dll".format(self.version)))
                shutil.copy("libmpdec-{}.dll.exp".format(self.version), os.path.join(dist_folder, "libmpdec-{}.exp".format(self.version)))
                shutil.copy("libmpdec-{}.dll.lib".format(self.version), os.path.join(dist_folder, "libmpdec-{}.lib".format(self.version)))
            else:
                shutil.copy("libmpdec-{}.lib".format(self.version), dist_folder)

    def _build_autotools(self):
        if self.settings.os == "Macos":
            tools.replace_in_file(os.path.join(self.source_folder, self._source_subfolder, "libmpdec", "Makefile.in"),
                                  "libmpdec.so", "libmpdec.dylib")
            # tools.replace_in_file(os.path.join(self.source_folder, self._source_subfolder, "Makefile.in"),
            #                       "libmpdec.a", "libmpdec.a")
            tools.replace_in_file(os.path.join(self.source_folder, self._source_subfolder, "Makefile.in"),
                                  "libmpdec.so", "libmpdec.dylib")
            tools.replace_in_file(os.path.join(self.source_folder, self._source_subfolder, "configure"),
                                  "libmpdec.so", "libmpdec.dylib")

        with tools.chdir(os.path.join(self.build_folder, self._source_subfolder)):
            autotools = AutoToolsBuildEnvironment(self, win_bash=self.settings.os == "Windows")
            autotools.configure()
            autotools.make()

    def package(self):
        if self.settings.compiler == "Visual Studio":
            distfolder = os.path.join(self.build_folder, self._source_subfolder, "vcbuild", "dist{}".format(32 if self.settings.arch == "x86" else 64))
            self.copy("vc*.h", src=os.path.join(self.build_folder, self._source_subfolder, "libmpdec"), dst="include")
            self.copy("*.h", src=distfolder, dst="include")
            self.copy("*.lib", src=distfolder, dst="lib")
            self.copy("*.dll", src=distfolder, dst="bin")
        else:
            with tools.chdir(os.path.join(self.build_folder, self._source_subfolder)):
                autotools = AutoToolsBuildEnvironment(self)
                autotools.install()

            if self.settings.os == "Linux":
                shared_ext = ".so"
                static_ext = ".a"
            elif self.settings.os == "Windows":
                shared_ext = ".dll"
                static_ext = ".a"
            elif self.settings.os == "Macos":
                shared_ext = ".dylib"
                static_ext = ".a"
            else:
                raise ConanException("Unknown configuration")
            self.output.info("Shared extension: '{}'".format(shared_ext))
            self.output.info("Static extension: '{}'".format(static_ext))

            allowedext = shared_ext if self.options.shared else static_ext
            self.output.info("self.options.shared={shared} ==> allowed ext={allowedext}".format(
                shared=self.options.shared, allowedext=allowedext))

            for package_dir in ("lib", "bin"):
                full_dir = os.path.join(self.package_folder, package_dir)
                if not os.path.isdir(full_dir):
                    continue
                self.output.info("Pruning {package_dir} directory...".format(package_dir=package_dir))
                with tools.chdir(full_dir):
                    for file in os.listdir("."):
                        _, _, fileext = file.partition("libmpdec")
                        if not fileext.startswith(allowedext):
                            self.output.info("{file} has no '{allowedext}'-extension --> remove".format(
                                file=file, allowedext=allowedext))
                            os.unlink(file)

        self.copy("LICENSE.txt",
                  src=os.path.join(self.source_folder, self._source_subfolder),
                  dst=os.path.join(self.package_folder, "licenses"))

    def package_info(self):
        libs = tools.collect_libs(self)
        if self.settings.compiler in ["gcc", "clang"]:
            libs.append("m")
        self.cpp_info.libs = libs
        if self.settings.compiler == "Visual Studio" and self.options.shared:
            self.cpp_info.defines = ["USE_DLL", ]
