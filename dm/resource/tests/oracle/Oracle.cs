// SPDX-License-Identifier: MIT
// Differential oracle using the project's existing MIT LibHac dependency.
using System;
using System.IO;
using System.Security.Cryptography;
using LibHac.Common;
using LibHac.Common.Keys;
using LibHac.Fs;
using LibHac.Fs.Fsa;
using LibHac.FsSystem;
using LibHac.Spl;
using LibHac.Tools.Fs;
using LibHac.Tools.FsSystem;
using LibHac.Tools.FsSystem.NcaUtils;
using LibHac.Tools.FsSystem.RomFs;

class Oracle {
    static IFileSystem OpenContainer(KeySet keys, string path) {
        var st0 = new LocalStorage(path, FileAccess.Read);
        byte[] magic = new byte[4]; st0.Read(0x100, magic).ThrowIfFailure();
        if (System.Text.Encoding.ASCII.GetString(magic) == "HEAD") {   // XCI: the card header's magic at 0x100
            var xci = new Xci(keys, st0);
            if (!xci.HasPartition(XciPartitionType.Secure)) throw new Exception($"no secure partition in {path}");
            return xci.OpenPartition(XciPartitionType.Secure);
        }
        var pfs = new PartitionFileSystem(); pfs.Initialize(st0).ThrowIfFailure(); return pfs;
    }
    static Nca ProgramNca(KeySet keys, string path) {
        var pfs=OpenContainer(keys, path);
        foreach(var ticket in pfs.EnumerateEntries("*",SearchOptions.Default)) {
            if(!ticket.Name.EndsWith(".tik")) continue;
            using var tf=new UniqueRef<IFile>(); pfs.OpenFile(ref tf.Ref,ticket.FullPath.ToU8Span(),OpenMode.Read).ThrowIfFailure();
            var bytes=new byte[0x2c0]; tf.Get.Read(out _,0,bytes,ReadOption.None).ThrowIfFailure();
            if(bytes[0x281]!=0) throw new Exception("non-common ticket");
            keys.ExternalKeySet.Add(new RightsId(bytes.AsSpan(0x2a0,16)),new AccessKey(bytes.AsSpan(0x180,16))).ThrowIfFailure();
        }
        foreach(var entry in pfs.EnumerateEntries("*",SearchOptions.Default)) {
            if(!entry.Name.EndsWith(".nca")) continue;
            var f=new UniqueRef<IFile>(); pfs.OpenFile(ref f.Ref,entry.FullPath.ToU8Span(),OpenMode.Read).ThrowIfFailure();
            var n=new Nca(keys,f.Release().AsStorage());
            if(n.Header.ContentType==NcaContentType.Program) return n;
        }
        throw new Exception("no Program NCA");
    }
    static void Main(string[] args) {
        var keys=ExternalKeyReader.ReadKeyFile(args[0]); var n=ProgramNca(keys,args[1]);
        var storage=args.Length>2?n.OpenStorageWithPatch(ProgramNca(keys,args[2]),NcaSectionType.Data,IntegrityCheckLevel.ErrorOnInvalid):n.OpenStorage(NcaSectionType.Data,IntegrityCheckLevel.ErrorOnInvalid);
        var fs=new RomFsFileSystem(storage);
        foreach(var e in fs.EnumerateEntries("*",SearchOptions.RecurseSubdirectories)) {
            if(e.Type==DirectoryEntryType.Directory) { Console.WriteLine($"d\t{e.FullPath}"); continue; }
            using var f=new UniqueRef<IFile>(); fs.OpenFile(ref f.Ref,e.FullPath.ToU8Span(),OpenMode.Read).ThrowIfFailure();
            using var hash=IncrementalHash.CreateHash(HashAlgorithmName.SHA256); var buf=new byte[8192]; long off=0;
            while(off<e.Size) { f.Get.Read(out long read,off,buf.AsSpan(0,(int)Math.Min(buf.Length,e.Size-off)),ReadOption.None).ThrowIfFailure(); if(read==0) throw new Exception("short read"); hash.AppendData(buf,0,(int)read); off+=read; }
            Console.WriteLine($"f\t{e.FullPath}\t{e.Size}\t{Convert.ToHexString(hash.GetHashAndReset()).ToLowerInvariant()}");
        }
    }
}
