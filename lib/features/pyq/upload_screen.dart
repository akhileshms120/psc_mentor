import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../../core/api.dart';
import '../../core/ui.dart';

/// Upload your own question paper (PDF or photos), optionally with its answer key.
class UploadScreen extends StatefulWidget {
  const UploadScreen({super.key});

  @override
  State<UploadScreen> createState() => _UploadScreenState();
}

class _UploadScreenState extends State<UploadScreen> {
  final _title = TextEditingController();
  final List<UploadFile> _paper = [];
  final List<UploadFile> _key = [];
  String _booklet = 'A';
  bool _busy = false;

  static const _extensions = ['pdf', 'jpg', 'jpeg', 'png', 'webp'];

  @override
  void dispose() {
    _title.dispose();
    super.dispose();
  }

  Future<void> _pick(List<UploadFile> into) async {
    try {
      final files = await FilePicker.pickFiles(type: FileType.custom, allowedExtensions: _extensions);
      final picked = [for (final f in files) UploadFile(f.name, await f.readAsBytes())];
      setState(() => into.addAll(picked));
      if (_title.text.isEmpty && into == _paper && picked.isNotEmpty) {
        _title.text = picked.first.name.replaceAll(RegExp(r'\.[^.]+$'), '');
      }
    } catch (e) {
      if (mounted) showError(context, e);
    }
  }

  Future<void> _upload() async {
    if (_paper.isEmpty) return showError(context, 'Add the question paper first.');
    if (_paper.where((f) => f.contentType == 'application/pdf').length > 1 ||
        (_paper.length > 1 && _paper.any((f) => f.contentType == 'application/pdf'))) {
      return showError(context, 'Upload the question paper as one PDF, or as photos of the pages.');
    }
    setState(() => _busy = true);
    try {
      await Api.instance.uploadPaper(
        title: _title.text.trim().isEmpty ? 'My question paper' : _title.text.trim(),
        paper: _paper,
        key: _key,
        booklet: _booklet,
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Uploaded. Reading the questions takes a minute or two; it will appear under Your papers.')));
      Navigator.of(context).pop();
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Upload a question paper')),
      body: PageFrame(
        title: 'Practise any paper',
        subtitle: 'Upload a PSC or coaching-centre paper as a PDF or as photos of each page. '
            'Add the answer key if you have it; otherwise the AI mentor works out the answers. '
            'Your uploads are private to you.',
        children: [
          TextField(controller: _title, decoration: const InputDecoration(labelText: 'Name for this paper')),
          const SizedBox(height: 20),
          _FileList(
            title: 'Question paper',
            files: _paper,
            onAdd: () => _pick(_paper),
            onRemove: (f) => setState(() => _paper.remove(f)),
          ),
          const SizedBox(height: 12),
          _FileList(
            title: 'Answer key (optional)',
            files: _key,
            onAdd: () => _pick(_key),
            onRemove: (f) => setState(() => _key.remove(f)),
          ),
          if (_key.isNotEmpty) ...[
            const SizedBox(height: 12),
            Row(children: [
              const Expanded(child: Text('Booklet code on your paper (PSC keys list answers per booklet)')),
              DropdownButton<String>(
                value: _booklet,
                items: [for (final b in ['A', 'B', 'C', 'D']) DropdownMenuItem(value: b, child: Text(b))],
                onChanged: (v) => setState(() => _booklet = v ?? 'A'),
              ),
            ]),
          ],
          const SizedBox(height: 24),
          FilledButton.icon(
            icon: const Icon(Icons.cloud_upload_outlined),
            label: Text(_busy ? 'Uploading…' : 'Upload and prepare test'),
            onPressed: _busy ? null : _upload,
          ),
        ],
      ),
    );
  }
}

class _FileList extends StatelessWidget {
  const _FileList({required this.title, required this.files, required this.onAdd, required this.onRemove});

  final String title;
  final List<UploadFile> files;
  final VoidCallback onAdd;
  final ValueChanged<UploadFile> onRemove;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Expanded(child: Text(title, style: Theme.of(context).textTheme.titleMedium)),
              TextButton.icon(onPressed: onAdd, icon: const Icon(Icons.attach_file), label: const Text('Add files')),
            ]),
            if (files.isEmpty) const Text('PDF, JPG or PNG'),
            for (final f in files)
              ListTile(
                dense: true,
                leading: Icon(f.contentType == 'application/pdf' ? Icons.picture_as_pdf : Icons.image_outlined),
                title: Text(f.name),
                subtitle: Text('${(f.bytes.length / 1024).round()} KB'),
                trailing: IconButton(icon: const Icon(Icons.close), onPressed: () => onRemove(f)),
              ),
          ],
        ),
      ),
    );
  }
}
