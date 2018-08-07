from beets.plugins import BeetsPlugin
from beets.ui import Subcommand
from beets import config
import pickle
import os
from shutil import copyfile
import hashlib

class BeetSync(BeetsPlugin):
    def __init__(self):
        super(BeetSync, self).__init__()
        self.config.add({
            'relative_to' : '/',
            'playlists_dir' : None,
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

        if not self.config['playlists_dir']:
            print('No playlist directory specified. Exiting')
            return
        if not self.config['sync']:
            print('No playlists specified. Exiting')
            return

        for i, od in enumerate(self.config['sync']):
            # sync all if none specified
            # sync only specified playlists
            if 'playlist' not in od.get():
                continue
            if not to_sync or od['playlist'].get() in to_sync:
                self.sync_one(od)

    def sync_one(self, od):
        # read config options
        rel_to = os.path.expanduser(self.config['relative_to'].get())
        pl_dir = self.config['playlists_dir'].get()
        pl_filename = od['playlist'].get()
        pl_file = os.path.expanduser(os.path.join(pl_dir, pl_filename))
        output_dir = os.path.expanduser(od['output_dir'].get())

        # create output directory if it doesn't exist
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        self.prev_data = self.load_obj(pl_filename)
        self.synced_data = {}
        if not self.prev_data:
            self.prev_data = {}

        # read playlist file
        files = []
        try:
            with open(pl_file, 'r') as f:
                for line in f:
                    files.append(line.strip())
        except FileNotFoundError:
            print('Error: playlist file not found')

        # sync files
        hasher = hashlib.md5()
        for f in files:
            output_path = f
            file_fullpath = os.path.join(rel_to, output_path)
            with open(file_fullpath, 'rb') as f:
                buf = f.read()
                hasher.update(buf)
                self.synced_data[file_fullpath] = hasher.hexdigest()
            output_fullpath = os.path.join(output_dir, output_path)
            self.sync_one_file(file_fullpath, output_fullpath)

        # delete removed files
        removed_data = {k:v for k,v in self.prev_data.items() if k not in self.synced_data}
        for f in removed_data:
            f = f[len(rel_to):].lstrip('/')
            to_del = os.path.join(output_dir, f)
            self.remove_one_file(to_del)

        # remove empty directories
        self.remove_empty_directories(output_dir)

        # save database
        self.save_obj(self.synced_data, pl_filename)

    def sync_one_file(self, src, dest):
        dest_dirname = os.path.dirname(dest)
        if not os.path.isdir(dest_dirname):
            os.makedirs(dest_dirname)
        if not os.path.exists(dest):
            copyfile(src, dest)
            print(src)
            return
        if src not in self.prev_data:
            copyfile(src, dest)
            print(src)
            return
        if self.prev_data[src] == self.synced_data[src]:
            return
        copyfile(src, dest)
        print(src)

    def remove_one_file(self, path):
        if os.path.exists(path):
            os.remove(path)
            print('removed %s' % path)

    def remove_empty_directories(self, path, remove_root=True):
        if not os.path.isdir(path):
            return
        # remove empty subfolders
        files = os.listdir(path)
        if len(files):
            for f in files:
                fullpath = os.path.join(path, f)
                if os.path.isdir(fullpath):
                    self.remove_empty_directories(fullpath)
        # if folder empty, delete it
        files = os.listdir(path)
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