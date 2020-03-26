import zipfile
import pathlib

    
def zip_files(zip_path, *files, **kwfiles):
    """Makes a zip file of real filenames and writes it to zip_path.
    Positional files will be written literally, 
    keyword arguments should be written as name_in_archive=path, ex.
    file="some_folder/some_file"
    """
    zf = zipfile.ZipFile(zip_path, "w")
    for f in files:
        zf.write(f)
    for arcname, realname in kwfiles.items():
        zf.write(realname, arcname=arcname)
    zf.close()


def zip_str(fname, data, zip_path):
    """Makes a zip with a single file, fname, with contents data and writes it to zip_fname.
    """
    zf = zipfile.ZipFile(zip_path, "w")
    zf.writestr(fname, data)
    zf.close()


def zip_dir(directory, zip_path):
    """Writes the zip of every file in directory to zip_path. Files in directory will be in root of zipfile, and files in subdirectories will be in subdirectories of zipfile. 
    """
    zf = zipfile.ZipFile(zip_path, 'w')
    base = pathlib.Path(directory)
    dirs = [base]
    while dirs:
        for p in dirs[0].iterdir():
            if p.is_dir():
                dirs.append(p)
            elif p.is_file():
                # when we are adding to the zip file we 
                # want files in the base to be in root of zipfile
                zf.write(p, arcname=p.relative_to(base))
        dirs = dirs[1:]
    zf.close()
