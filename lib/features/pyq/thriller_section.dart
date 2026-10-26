import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/api.dart';
import '../../core/models.dart';
import '../../core/ui.dart';

/// Kerala PSC papers posted on PSC Thriller (pscthriller.com): the official paper with PSC's
/// answer key in one PDF. Shown with credit and a link to each post.
class ThrillerSection extends StatefulWidget {
  const ThrillerSection({super.key, required this.papers, required this.onImported});

  final List<Paper> papers;
  final VoidCallback onImported;

  @override
  State<ThrillerSection> createState() => _ThrillerSectionState();
}

class _ThrillerSectionState extends State<ThrillerSection> {
  late Future<List<ThrillerPost>> _posts = Api.instance.thrillerPapers();
  String _level = 'degree';
  bool _showAll = false;

  static const _levels = {'degree': 'Degree level', 'general': 'Other general', 'all': 'All'};

  Future<void> _import(ThrillerPost post) async {
    try {
      await Api.instance.importThriller(post.url);
      widget.onImported();
    } catch (e) {
      if (mounted) showError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final byUrl = {for (final p in widget.papers) if (p.originUrl != null) p.originUrl!: p};
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SectionTitle('From PSC Thriller'),
        Row(children: [
          const Expanded(
            child: Text('Official PSC papers with their answer keys, as posted on pscthriller.com. '
                'Thanks to PSC Thriller for collecting them.'),
          ),
          TextButton(
            onPressed: () => launchUrl(Uri.parse('https://www.pscthriller.com/'), mode: LaunchMode.externalApplication),
            child: const Text('Visit site'),
          ),
        ]),
        const SizedBox(height: 8),
        Wrap(spacing: 8, children: [
          for (final e in _levels.entries)
            ChoiceChip(label: Text(e.value), selected: _level == e.key, onSelected: (_) => setState(() => _level = e.key)),
        ]),
        const SizedBox(height: 8),
        FutureBuilder<List<ThrillerPost>>(
          future: _posts,
          builder: (context, snap) {
            if (snap.hasError) {
              return ErrorCard(snap.error!, onRetry: () => setState(() => _posts = Api.instance.thrillerPapers()));
            }
            if (!snap.hasData) return const Padding(padding: EdgeInsets.all(16), child: LinearProgressIndicator());
            final posts = snap.data!
                .where((p) => p.level != 'technical' && (_level == 'all' || p.level == _level))
                .toList();
            final shown = _showAll ? posts : posts.take(10).toList();
            return Column(children: [
              for (final post in shown)
                Card(
                  child: ListTile(
                    title: Text(post.title),
                    subtitle: Text([post.published, if (post.paperCode != null) 'Code ${post.paperCode}'].join(' · ')),
                    onLongPress: () => launchUrl(Uri.parse(post.url), mode: LaunchMode.externalApplication),
                    trailing: _Status(paper: byUrl[post.url], onImport: () => _import(post)),
                  ),
                ),
              if (posts.length > shown.length)
                TextButton(onPressed: () => setState(() => _showAll = true), child: Text('Show all ${posts.length}')),
            ]);
          },
        ),
      ],
    );
  }
}

class _Status extends StatelessWidget {
  const _Status({required this.paper, required this.onImport});
  final Paper? paper;
  final VoidCallback onImport;

  @override
  Widget build(BuildContext context) {
    final p = paper;
    if (p != null && p.busy) {
      return const SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2));
    }
    if (p != null && p.status == 'done') return const Icon(Icons.check_circle, color: Colors.green);
    return OutlinedButton(onPressed: onImport, child: Text(p?.status == 'failed' ? 'Retry' : 'Import'));
  }
}
