import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api.dart';
import '../../core/models.dart';
import '../../core/ui.dart';
import '../analysis/analysis_screen.dart';
import '../mentor/mentor_screen.dart';

const _letters = ['A', 'B', 'C', 'D'];

/// Creates a test (which can take a while if the mentor writes new questions) and opens it.
Future<void> startTest(BuildContext context, Future<TestInfo> Function() create) async {
  final navigator = Navigator.of(context);
  showDialog<void>(
    context: context,
    barrierDismissible: false,
    builder: (_) => const AlertDialog(
      content: Row(children: [
        CircularProgressIndicator(),
        SizedBox(width: 20),
        Expanded(child: Text('Preparing your test…\nNew questions may take up to a minute.')),
      ]),
    ),
  );
  try {
    final test = await create();
    navigator.pop();
    await navigator.push(MaterialPageRoute<void>(builder: (_) => TestScreen(test: test)));
  } catch (e) {
    navigator.pop();
    if (context.mounted) showError(context, e);
  }
}

/// Opens a test from history: the review if it was submitted, otherwise the test itself.
Future<void> openTest(BuildContext context, int testId) async {
  try {
    final test = await Api.instance.test(testId);
    if (!context.mounted) return;
    final page = test.submitted ? ResultScreen(result: await Api.instance.result(testId)) : TestScreen(test: test);
    if (context.mounted) await Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => page));
  } catch (e) {
    if (context.mounted) showError(context, e);
  }
}

class TestScreen extends StatefulWidget {
  const TestScreen({super.key, required this.test});
  final TestInfo test;

  @override
  State<TestScreen> createState() => _TestScreenState();
}

class _TestScreenState extends State<TestScreen> {
  late final Map<int, int?> _selected = {for (final q in widget.test.questions) q.id: null};
  final Map<int, int> _timeMs = {};
  final Stopwatch _questionClock = Stopwatch()..start();
  late Duration _remaining = Duration(minutes: widget.test.durationMinutes);
  Timer? _timer;
  int _index = 0;
  bool _submitting = false;

  List<Question> get _questions => widget.test.questions;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      setState(() => _remaining -= const Duration(seconds: 1));
      if (_remaining <= Duration.zero) _submit(timeUp: true);
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  void _go(int index) {
    final q = _questions[_index];
    _timeMs[q.id] = (_timeMs[q.id] ?? 0) + _questionClock.elapsedMilliseconds;
    _questionClock.reset();
    setState(() => _index = index);
  }

  Future<void> _submit({bool timeUp = false}) async {
    if (_submitting) return;
    if (!timeUp) {
      final unanswered = _selected.values.where((v) => v == null).length;
      final ok = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Submit test?'),
          content: Text(unanswered == 0
              ? 'All questions answered.'
              : '$unanswered unanswered. Skipped questions carry no negative mark.'),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Keep going')),
            FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Submit')),
          ],
        ),
      );
      if (ok != true) return;
    }
    _timer?.cancel();
    _go(_index);
    setState(() => _submitting = true);
    try {
      final result = await Api.instance.submit(widget.test.id, _selected, _timeMs);
      if (!mounted) return;
      Navigator.of(context).pushReplacement(MaterialPageRoute<void>(builder: (_) => ResultScreen(result: result)));
    } catch (e) {
      if (!mounted) return;
      setState(() => _submitting = false);
      showError(context, e);
    }
  }

  void _palette() {
    showModalBottomSheet<void>(
      context: context,
      builder: (context) => Padding(
        padding: const EdgeInsets.all(16),
        child: Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (var i = 0; i < _questions.length; i++)
              ChoiceChip(
                label: Text('${i + 1}'),
                selected: _selected[_questions[i].id] != null,
                onSelected: (_) {
                  Navigator.pop(context);
                  _go(i);
                },
              ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final q = _questions[_index];
    final answered = _selected.values.where((v) => v != null).length;
    final mm = _remaining.inMinutes.toString().padLeft(2, '0');
    final ss = (_remaining.inSeconds % 60).toString().padLeft(2, '0');
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) async {
        if (didPop) return;
        final leave = await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
            title: const Text('Leave test?'),
            content: const Text('Your answers on this screen will be lost. You can restart it from Tests.'),
            actions: [
              TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Stay')),
              TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Leave')),
            ],
          ),
        );
        if (leave == true && context.mounted) Navigator.of(context).pop();
      },
      child: Scaffold(
        appBar: AppBar(
          title: Text(widget.test.title, overflow: TextOverflow.ellipsis),
          actions: [
            Center(
              child: Text('$mm:$ss',
                  style: TextStyle(
                    fontFeatures: const [FontFeature.tabularFigures()],
                    color: _remaining.inMinutes < 5 ? Theme.of(context).colorScheme.error : null,
                  )),
            ),
            IconButton(onPressed: _palette, icon: const Icon(Icons.grid_view), tooltip: 'All questions'),
          ],
        ),
        body: SafeArea(
          child: Column(
            children: [
              LinearProgressIndicator(value: answered / _questions.length),
              Expanded(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.all(20),
                  child: Center(
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 760),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Question ${_index + 1} of ${_questions.length} · ${q.sourceLabel}',
                              style: Theme.of(context).textTheme.labelLarge),
                          const SizedBox(height: 12),
                          Text(q.stem, style: Theme.of(context).textTheme.titleLarge),
                          const SizedBox(height: 20),
                          for (var i = 0; i < q.options.length; i++)
                            _OptionTile(
                              letter: _letters[i],
                              text: q.options[i],
                              selected: _selected[q.id] == i,
                              onTap: () => setState(() => _selected[q.id] = _selected[q.id] == i ? null : i),
                            ),
                          const SizedBox(height: 8),
                          Text('Tap a selected option again to clear it. Wrong answers cost '
                              '${widget.test.negativeMark.toStringAsFixed(2)} marks.',
                              style: Theme.of(context).textTheme.bodySmall),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
                child: Row(
                  children: [
                    OutlinedButton(onPressed: _index > 0 ? () => _go(_index - 1) : null, child: const Text('Previous')),
                    const Spacer(),
                    if (_index < _questions.length - 1)
                      FilledButton(onPressed: () => _go(_index + 1), child: const Text('Next'))
                    else
                      FilledButton(
                        onPressed: _submitting ? null : _submit,
                        child: Text(_submitting ? 'Submitting…' : 'Submit'),
                      ),
                    if (_index < _questions.length - 1) ...[
                      const SizedBox(width: 8),
                      TextButton(onPressed: _submitting ? null : _submit, child: const Text('Submit')),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _OptionTile extends StatelessWidget {
  const _OptionTile({required this.letter, required this.text, required this.selected, required this.onTap});

  final String letter;
  final String text;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      color: selected ? scheme.primaryContainer : null,
      child: ListTile(
        onTap: onTap,
        leading: CircleAvatar(
          backgroundColor: selected ? scheme.primary : scheme.surfaceContainerHighest,
          foregroundColor: selected ? scheme.onPrimary : scheme.onSurface,
          child: Text(letter),
        ),
        title: Text(text),
      ),
    );
  }
}

class ResultScreen extends StatelessWidget {
  const ResultScreen({super.key, required this.result});
  final TestInfo result;

  @override
  Widget build(BuildContext context) {
    final r = result;
    final accuracy = (r.correct! + r.wrong!) == 0 ? null : r.correct! / (r.correct! + r.wrong!);
    return Scaffold(
      appBar: AppBar(title: Text(r.title, overflow: TextOverflow.ellipsis)),
      body: PageFrame(
        title: '${r.score!.toStringAsFixed(2)} / ${r.maxScore!.toStringAsFixed(0)}',
        subtitle: '${r.correct} correct · ${r.wrong} wrong · ${r.skipped} skipped · accuracy ${pct(accuracy)}'
            ' · ${(r.wrong! * r.negativeMark).toStringAsFixed(2)} marks lost to negative marking',
        children: [
          if (r.type == 'diagnostic' || r.type == 'monthly')
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: FilledButton.icon(
                icon: const Icon(Icons.insights),
                label: const Text('See your strength report & time plan'),
                onPressed: () => Navigator.of(context)
                    .pushReplacement(MaterialPageRoute<void>(builder: (_) => const AnalysisScreen())),
              ),
            ),
          if (r.topics.isNotEmpty) ...[
            const SectionTitle('By topic'),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final t in r.topics)
                  Chip(label: Text('${t.topic}: ${t.correct}/${t.correct + t.wrong + t.skipped}')),
              ],
            ),
          ],
          const SectionTitle('Review answers'),
          for (var i = 0; i < r.questions.length; i++) _ReviewCard(number: i + 1, question: r.questions[i]),
        ],
      ),
    );
  }
}

class _ReviewCard extends StatelessWidget {
  const _ReviewCard({required this.number, required this.question});
  final int number;
  final Question question;

  @override
  Widget build(BuildContext context) {
    final q = question;
    final scheme = Theme.of(context).colorScheme;
    final status = q.selectedIndex == null
        ? ('Skipped', scheme.outline, Icons.remove_circle_outline)
        : q.selectedIndex == q.answerIndex
            ? ('Correct', Colors.green.shade700, Icons.check_circle)
            : ('Wrong', scheme.error, Icons.cancel);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Icon(status.$3, color: status.$2, size: 18),
              const SizedBox(width: 6),
              Text('$number · ${status.$1}', style: TextStyle(color: status.$2, fontWeight: FontWeight.w600)),
              const Spacer(),
              Text('${q.topic ?? ''} · ${q.sourceLabel}', style: Theme.of(context).textTheme.bodySmall),
            ]),
            const SizedBox(height: 8),
            Text(q.stem, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            for (var i = 0; i < q.options.length; i++)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 2),
                child: Text(
                  '${_letters[i]}. ${q.options[i]}'
                  '${i == q.answerIndex ? '  ✓' : ''}${i == q.selectedIndex && i != q.answerIndex ? '  (your answer)' : ''}',
                  style: TextStyle(
                    color: i == q.answerIndex ? Colors.green.shade700 : (i == q.selectedIndex ? scheme.error : null),
                    fontWeight: i == q.answerIndex ? FontWeight.w600 : null,
                  ),
                ),
              ),
            if (q.explanation != null && q.explanation!.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(q.explanation!, style: Theme.of(context).textTheme.bodyMedium),
            ],
            if (q.sourceRef != null) ...[
              const SizedBox(height: 4),
              Text('Based on ${q.sourceRef}', style: Theme.of(context).textTheme.bodySmall),
            ],
            Align(
              alignment: Alignment.centerRight,
              child: TextButton.icon(
                icon: const Icon(Icons.school_outlined),
                label: const Text('Ask mentor'),
                onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(
                  builder: (_) => MentorScreen(
                    standalone: true,
                    initialMessage: 'Explain this question and the concept behind it:\n${q.stem}\n'
                        '${[for (var i = 0; i < q.options.length; i++) '${_letters[i]}. ${q.options[i]}'].join('\n')}\n'
                        'Correct answer: ${q.answerIndex == null ? '?' : _letters[q.answerIndex!]}'
                        '${q.selectedIndex != null && q.selectedIndex != q.answerIndex ? '. I chose ${_letters[q.selectedIndex!]}.' : ''}',
                  ),
                )),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
