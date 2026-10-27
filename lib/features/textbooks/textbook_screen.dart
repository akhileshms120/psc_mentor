import 'dart:async';

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/api.dart';
import '../../core/models.dart';
import '../../core/ui.dart';
import '../tests/test_runner.dart';

/// NCERT chapters mapped to the syllabus, and the practice questions the AI wrote from them.
class TextbookScreen extends StatefulWidget {
  const TextbookScreen({super.key});

  @override
  State<TextbookScreen> createState() => _TextbookScreenState();
}

class _TextbookScreenState extends State<TextbookScreen> {
  Timer? _poll;

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  Future<List<NcertChapter>> _load() async {
    final chapters = await Api.instance.ncertChapters();
    _poll?.cancel();
    // While a chapter is being written, refresh until it finishes.
    if (chapters.any((c) => c.status == 'working')) {
      _poll = Timer(const Duration(seconds: 6), Api.instance.changed);
    }
    return chapters;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('NCERT textbook questions')),
      body: Loader<List<NcertChapter>>(
        load: _load,
        builder: (context, chapters, reload) {
          final total = chapters.fold<int>(0, (s, c) => s + c.questions);
          final bySubject = <String, List<NcertChapter>>{};
          for (final c in chapters) {
            bySubject.putIfAbsent(c.subject, () => []).add(c);
          }
          return PageFrame(
            title: '$total questions from ${chapters.where((c) => c.questions > 0).length} chapters',
            subtitle: 'NCERT chapters (Classes 6–12) that teach the Degree Prelims syllabus. The AI writes '
                'PSC-style questions using only facts stated in a chapter. New chapters are also done '
                'automatically a few at a time.',
            onRefresh: reload,
            children: [
              FilledButton.icon(
                icon: const Icon(Icons.play_arrow),
                label: const Text('Practice all textbook questions'),
                onPressed: total == 0 ? null : () => startTest(context, () => Api.instance.createTest('textbook')),
              ),
              for (final entry in bySubject.entries) ...[
                SectionTitle(entry.key),
                for (final c in entry.value) _ChapterCard(chapter: c),
              ],
            ],
          );
        },
      ),
    );
  }
}

class _ChapterCard extends StatelessWidget {
  const _ChapterCard({required this.chapter});
  final NcertChapter chapter;

  Future<void> _make(BuildContext context) async {
    try {
      await Api.instance.makeChapterQuestions(chapter.id);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Writing questions from this chapter. This takes about a minute.')));
      }
    } catch (e) {
      if (context.mounted) showError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = chapter;
    final theme = Theme.of(context);
    final status = switch (c.status) {
      'working' => 'Writing questions…',
      'failed' => 'Could not write questions: ${c.error ?? 'unknown error'}',
      _ when c.questions > 0 => '${c.questions} questions',
      _ => 'No questions yet',
    };
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Class ${c.classNo} · ${c.book} · Ch ${c.chapter}', style: theme.textTheme.labelLarge),
            Text(c.title, style: theme.textTheme.titleMedium),
            const SizedBox(height: 4),
            Text('Syllabus: ${c.topics.join(', ')}', style: theme.textTheme.bodySmall),
            const SizedBox(height: 4),
            Row(children: [
              if (c.status == 'working')
                const Padding(
                  padding: EdgeInsets.only(right: 8),
                  child: SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2)),
                ),
              Expanded(child: Text(status)),
            ]),
            const SizedBox(height: 8),
            Wrap(spacing: 8, runSpacing: 4, children: [
              OutlinedButton.icon(
                icon: const Icon(Icons.menu_book_outlined),
                label: const Text('Read'),
                onPressed: () => launchUrl(Uri.parse(c.url), mode: LaunchMode.externalApplication),
              ),
              OutlinedButton.icon(
                icon: const Icon(Icons.auto_awesome_outlined),
                label: Text(c.questions > 0 ? 'Make more' : 'Make questions'),
                onPressed: c.status == 'working' ? null : () => _make(context),
              ),
              FilledButton.tonal(
                onPressed: c.questions == 0
                    ? null
                    : () => startTest(context, () => Api.instance.createTest('textbook', chapterId: c.id)),
                child: const Text('Practice'),
              ),
            ]),
          ],
        ),
      ),
    );
  }
}
