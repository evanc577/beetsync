from beets.plugins import BeetsPlugin
from beets.ui import Subcommand
from beets import config
import pickle
import os
import subprocess
from shutil import copyfile
import hashlib
from collections import OrderedDict

class BeetSync(BeetsPlugin):
    def __init__(self):
        super(BeetSync, self).__init__()
        self.config.add({
            'relative_to' : '/',
            'playlist_dir' : None,
            'sync' : None,
            })

    def commands(self):
        cmds = Subcommand('sync')
        cmds.func = self.sync
        return [cmds]

    def sync(self, lib, opts, args):
        to_sync = args

        self.cur_dir = os.path.dirname(os.path.realpath(__file__))
        self.data_path = os.path.join(self.cur_dir, 'data')
        if not os.path.exists(self.data_path):
            os.makedirs(self.data_path)

        if not self.config['playlist_dir']:
            print('No playlist directory specified. Exiting')
            return
        if not self.config['sync']:
            print('No sync configuration specified. Exiting')
            return

        for i, od in enumerate(self.config['sync']):
            # sync all if none specified
            # sync only specified playlists
            if 'playlists' not in od.get():
                continue
            if 'output_dir' not in od.get():
                continue
            if not to_sync or od['playlists'].get() in to_sync:
                self.sync_one(od)

    def sync_one(self, od):
        # read config options
        rel_to = os.path.expanduser(self.config['relative_to'].get())
        pl_dir = self.config['playlist_dir'].get()
        pl_list = od['playlists'].get(list)
        output_dir = os.path.expanduser(od['output_dir'].get())
        convert_list = None
        if 'convert' in od.get():
            convert_list = od['convert'].get()
        self.pl_output_dir = None
        if 'playlist_output_dir' in od.get():
            self.pl_output_dir = os.path.expanduser(od['playlist_output_dir'].get())
        self.pl_output_prefix = None
        if 'playlist_output_prefix' in od.get():
            self.pl_output_prefix = od['playlist_output_prefix'].get()

        self.convert_dict = {}
        if convert_list:
            for conv in convert_list:
                for filetype in conv.items():
                    self.convert_dict[filetype[0].lower()] = filetype[1]

        self.symlink = False
        if 'symlink' in od.get() and od['symlink'].get(bool):
            self.symlink = True

        # create output directory if it doesn't exist
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        hasher = hashlib.sha1()
        hasher.update(output_dir.encode('utf-8'))
        data_filename = hasher.hexdigest()
        self.prev_data = self.load_obj(data_filename)
        self.synced_data = {}
        if not self.prev_data:
            self.prev_data = {}

        # read playlist file
        files = OrderedDict()
        self.output_playlist = OrderedDict()
        for playlist in pl_list:
            pl_file = os.path.expanduser(os.path.join(pl_dir, playlist))
            self.output_playlist[playlist] = []
            try:
                with open(pl_file, 'r') as f:
                    for line in f:
                        files[line.strip()] = True
                        self.add_to_output_playlist(playlist, line.strip())
                        
            except FileNotFoundError:
                print('Error: playlist file not found')
                return
            if self.pl_output_dir:
                pl_output_path = os.path.expanduser(os.path.join(\
                        self.pl_output_dir, playlist))
                if not os.path.exists(self.pl_output_dir):
                    os.makedirs(self.pl_output_dir)
                with open(pl_output_path, 'w') as f:
                    for pl in self.output_playlist[playlist]:
                        f.write('%s\n' % (pl))


        # sync files
        synced_covers = set()
        extensions = {".jpg", ".jpeg", ".tiff", ".bmp", ".heif", ".heic", ".png", ".gif"}
        for f in files:
            output_path = f
            file_fullpath = os.path.join(rel_to, output_path)
            self.synced_data[file_fullpath] = os.path.getmtime(file_fullpath)
            output_fullpath = os.path.join(output_dir, output_path)
            self.sync_one_file(file_fullpath, output_fullpath)
            files = os.listdir(os.path.dirname(file_fullpath))
            for f in files:
                if 'cover' in f.lower() and any(f.lower().endswith(ext) for ext in extensions):
                    cover_dirname = os.path.dirname(file_fullpath)
                    cover_fullpath = os.path.join(cover_dirname, f)
                    if cover_fullpath in synced_covers:
                        break
                    cover_output_dirname = os.path.dirname(output_fullpath)
                    cover_output_fullpath = os.path.join(cover_output_dirname, f)
                    self.synced_data[cover_fullpath] = os.path.getmtime(cover_fullpath)
                    self.sync_one_cover(cover_fullpath, cover_output_fullpath)
                    synced_covers.add(cover_fullpath)


        # delete removed files
        removed_data = {k:v for k,v in self.prev_data.items() if k not in self.synced_data}
        for f in removed_data:
            f = f[len(rel_to):].lstrip('/')
            to_del = os.path.join(output_dir, f)
            self.remove_one_file(to_del)
            filename_lower = to_del.lower()
            for filetype in self.convert_dict:
                if filename_lower.endswith(filetype):
                    to_del_test = to_del[:-1*len(filetype)]
                    to_del_test = to_del_test + self.convert_dict[filetype]['ext']
                    if os.path.isfile(to_del_test):
                        self.remove_one_file(to_del_test)
                        break

        # remove empty directories
        self.remove_empty_directories(output_dir)

        # save database
        self.save_obj(self.synced_data, data_filename)

    def add_to_output_playlist(self, playlist, path):
        prefix = ''
        if self.pl_output_prefix:
            prefix = self.pl_output_prefix
        path_lower = path.lower()
        for filetype in self.convert_dict:
            if path_lower.endswith(filetype):
                path_test = path[:-1*len(filetype)]
                path_test = path_test + self.convert_dict[filetype]['ext']
                output_fullpath = os.path.join(prefix, path_test)
                self.output_playlist[playlist].append(output_fullpath)
                return
        output_fullpath = os.path.join(prefix, path)
        self.output_playlist[playlist].append(output_fullpath)



    # sync cover art
    def sync_one_cover(self, src, dest):
        dest_dirname = os.path.dirname(dest)
        if not os.path.isdir(dest_dirname):
            os.makedirs(dest_dirname)
        if src not in self.prev_data:
            self.copy_file(src, dest)
            return
        if not os.path.isfile(dest):
            self.copy_file(src, dest)
        if self.prev_data[src] == self.synced_data[src]:
            return
        self.copy_file(src, dest)

    def sync_one_file(self, src, dest):
        dest_dirname = os.path.dirname(dest)
        if not os.path.isdir(dest_dirname):
            os.makedirs(dest_dirname)
        if src not in self.prev_data:
            self.copy_file(src, dest)
            return
        dest_lower = dest.lower()
        for filetype in self.convert_dict:
            if dest_lower.endswith(filetype):
                dest_test = dest[:-1*len(filetype)]
                dest_test = dest_test + self.convert_dict[filetype]['ext']
                if os.path.isfile(dest_test):
                    return
        if not os.path.isfile(dest):
            self.copy_file(src, dest)
        if self.prev_data[src] == self.synced_data[src]:
            return
        self.copy_file(src, dest)

    def copy_file(self, src, dest):
        # convert if applicable
        src_lower = src.lower()
        for filetype in self.convert_dict:
            if src_lower.endswith(filetype):
                in_file = src[:-1*len(filetype)]
                dest_dirname = os.path.dirname(dest)
                out_file = os.path.join(dest_dirname,
                        os.path.basename(in_file) + self.convert_dict[filetype]['ext'])
                cmd = []
                cmd = [str(x) for x in self.convert_dict[filetype]['cmd1']]
                cmd.append(src)
                cmd.extend([str(x) for x in self.convert_dict[filetype]['cmd2']])
                cmd.append(out_file)
                subprocess.run(cmd, stderr=subprocess.DEVNULL)
                print(out_file)
                return

        if self.symlink:
            os.symlink(src, dest)
        else:
            copyfile(src, dest)
        print(dest)


    def remove_one_file(self, path):
        if os.path.islink(path):
            os.unlink(path)
            print('removed %s' % path)
            return
        if os.path.isfile(path):
            os.remove(path)
            print('removed %s' % path)
            return

    def remove_empty_directories(self, path, remove_root=True):
        if not os.path.isdir(path):
            return
        if os.path.basename(path).startswith('.'):
            return
        # remove empty subfolders
        files = os.listdir(path)
        if len(files):
            for f in files:
                if f.startswith('.'):
                    return
                fullpath = os.path.join(path, f)
                if os.path.isdir(fullpath):
                    self.remove_empty_directories(fullpath)
        # if folder empty, delete it
        files = os.listdir(path)
        empty = True
        for f in files:
            f_lower = f.lower()
            if 'cover' not in f_lower:
                empty = False
        if empty:
            for f in files:
                f_lower = f.lower()
                if 'cover' in f_lower:
                    os.remove(f)
        if len(files) == 0 and remove_root:
            os.rmdir(path)


    def save_obj(self, obj, name):
        filepath = os.path.join(self.data_path, name + '.pkl')
        with open(filepath, 'wb') as f:
            pickle.dump(obj, f, pickle.HIGHEST_PROTOCOL)

    def load_obj(self, name):
        filepath = os.path.join(self.data_path, name + '.pkl')
        try:
            with open(filepath, 'rb') as f:
                return pickle.load(f)
        except FileNotFoundError:
            return None
