import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api.dart';
import '../../core/models.dart';
import '../../core/ui.dart';
import '../tests/test_runner.dart';
import 'paper_detail_screen.dart';
import 'thriller_section.dart';
import 'upload_screen.dart';

/// Previous question papers: imported ones to practise, and the official PSC answer-key
/// listing to import more from.
class PyqScreen extends StatefulWidget {
  const PyqScreen({super.key});

  @override
  State<PyqScreen> createState() => _PyqScreenState();
}

class _PyqScreenState extends State<PyqScreen> {
  List<Paper> _papers = [];
  final List<PaperListing> _listing = [];
  int _page = 0;
  bool _loadingListing = false;
  Object? _listingError;
  Object? _papersError;
  String _medium = 'All';
  Timer? _poll;

  static const _mediums = ['All', 'English', 'Malayalam'];

  @override
  void initState() {
    super.initState();
    _loadPapers();
    _loadListing();
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  Future<void> _loadPapers() async {
    try {
      final papers = await Api.instance.papers();
      if (!mounted) return;
      final wasBusy = _papers.any((p) => p.busy);
      setState(() {
        _papers = papers;
        _papersError = null;
      });
      final busy = papers.any((p) => p.busy);
      _poll?.cancel();
      if (busy) _poll = Timer(const Duration(seconds: 4), _loadPapers);
      if (wasBusy && !busy) Api.instance.changed(); // new questions in the bank
    } catch (e) {
      if (mounted) setState(() => _papersError = e);
    }
  }

  Future<void> _loadListing({bool more = false}) async {
    if (_loadingListing) return;
    setState(() => _loadingListing = true);
    try {
      final page = more ? _page + 1 : 0;
      final rows = await Api.instance.pscPapers(page);
      if (!mounted) return;
      setState(() {
        if (!more) _listing.clear();
        _listing.addAll(rows);
        _page = page;
        _listingError = null;
      });
    } catch (e) {
      if (mounted) setState(() => _listingError = e);
    } finally {
      if (mounted) setState(() => _loadingListing = false);
    }
  }

  Future<void> _import(PaperListing listing) async {
    try {
      await Api.instance.importPaper(listing);
      await _loadPapers();
    } catch (e) {
      if (mounted) showError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final imported = {for (final p in _papers) p.keyUrl: p};
    final visible = _listing.where((l) => _medium == 'All' || l.medium == _medium).toList();
    final uploads = _papers.where((p) => p.uploaded).toList();
    final official = _papers.where((p) => !p.uploaded).toList();
    return PageFrame(
      title: 'Question Papers',
      subtitle: 'The latest official Kerala PSC papers, plus papers you upload yourself.',
      actions: [
        FilledButton.icon(
          icon: const Icon(Icons.upload_file),
          label: const Text('Upload'),
          onPressed: () async {
            await Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const UploadScreen()));
            _loadPapers();
          },
        ),
      ],
      onRefresh: () async {
        await Future.wait([_loadPapers(), _loadListing()]);
      },
      children: [
        if (_papersError != null) ErrorCard(_papersError!, onRetry: _loadPapers),
        const SectionTitle('Your uploaded papers'),
        if (uploads.isEmpty)
          const Text('Upload a PSC or coaching paper (PDF or photos) to take it as a timed test and '
              'review your answers.'),
        for (final p in uploads) _PaperTile(paper: p),
        Row(children: [
          const Expanded(child: SectionTitle('Latest PSC papers in your question bank')),
          TextButton.icon(
            icon: const Icon(Icons.sync),
            label: const Text('Fetch latest'),
            onPressed: () async {
              try {
                await Api.instance.syncNow();
                if (context.mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                      content: Text('Checking keralapsc.gov.in for new general-studies papers…')));
                }
                Future.delayed(const Duration(seconds: 3), _loadPapers);
              } catch (e) {
                if (context.mounted) showError(context, e);
              }
            },
          ),
        ]),
        if (official.isEmpty)
          const Text('None yet. The server imports the newest degree-level and general papers '
              'automatically, or import one below.'),
        for (final p in official) _PaperTile(paper: p),
        ThrillerSection(papers: _papers, onImported: _loadPapers),
        const SectionTitle('Official answer keys'),
        Wrap(
          spacing: 8,
          children: [
            for (final m in _mediums)
              ChoiceChip(label: Text(m), selected: _medium == m, onSelected: (_) => setState(() => _medium = m)),
          ],
        ),
        const SizedBox(height: 8),
        if (_listingError != null) ErrorCard(_listingError!, onRetry: _loadListing),
        for (final l in visible)
          Card(
            child: ListTile(
              title: Text(l.title),
              subtitle: Text([
                if (l.paperCode != null) 'Code ${l.paperCode}',
                if (l.medium != null) l.medium!,
                if (l.testDate != null) l.testDate!,
                if (l.keyType != null) l.keyType!,
                if (l.questionUrl == null) 'question paper not published',
              ].join(' · ')),
              trailing: _ImportButton(
                listing: l,
                paper: imported[l.keyUrl],
                onImport: () => _import(l),
              ),
            ),
          ),
        const SizedBox(height: 8),
        Center(
          child: _loadingListing
              ? const CircularProgressIndicator()
              : OutlinedButton(onPressed: () => _loadListing(more: true), child: const Text('Load older papers')),
        ),
      ],
    );
  }

}

class _ImportButton extends StatelessWidget {
  const _ImportButton({required this.listing, required this.paper, required this.onImport});

  final PaperListing listing;
  final Paper? paper;
  final VoidCallback onImport;

  @override
  Widget build(BuildContext context) {
    final p = paper;
    if (p != null && p.busy) {
      return const SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2));
    }
    if (p != null && p.status == 'done') return const Icon(Icons.check_circle, color: Colors.green);
    return OutlinedButton(
      onPressed: listing.questionUrl == null ? null : onImport,
      child: Text(p?.status == 'failed' ? 'Retry' : 'Import'),
    );
  }
}

class _PaperTile extends StatelessWidget {
  const _PaperTile({required this.paper});
  final Paper paper;

  @override
  Widget build(BuildContext context) {
    final p = paper;
    final status = switch (p.status) {
      'done' => '${p.questionCount} questions · ${p.answersLabel}',
      'failed' => 'Import failed: ${p.error ?? 'unknown error'}',
      'extracting' => 'Reading questions…',
      _ => 'Downloading…',
    };
    return Card(
      child: ListTile(
        leading: Icon(p.status == 'done'
            ? Icons.history_edu
            : p.status == 'failed'
                ? Icons.error_outline
                : Icons.downloading),
        title: Text(p.title),
        subtitle: Text('${[p.paperCode, p.medium, p.testDate, if (p.origin != null) 'via ${p.origin}'].whereType<String>().join(' · ')}\n$status'),
        isThreeLine: true,
        onTap: () => Navigator.of(context)
            .push(MaterialPageRoute<void>(builder: (_) => PaperDetailScreen(paperId: p.id))),
        trailing: p.status == 'done'
            ? FilledButton.tonal(
                onPressed: () => startTest(context, () => Api.instance.createTest('paper', paperId: p.id)),
                child: const Text('Take test'),
              )
            : null,
      ),
    );
  }
}
