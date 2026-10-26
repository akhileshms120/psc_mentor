import 'package:flutter/material.dart';

import 'api.dart';

String pct(double? value) => value == null ? '—' : '${(value * 100).round()}%';

class PageFrame extends StatelessWidget {
  const PageFrame({
    super.key,
    required this.title,
    required this.subtitle,
    required this.children,
    this.actions = const [],
    this.onRefresh,
  });

  final String title;
  final String subtitle;
  final List<Widget> children;
  final List<Widget> actions;
  final Future<void> Function()? onRefresh;

  @override
  Widget build(BuildContext context) {
    final content = SingleChildScrollView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.all(24),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 1100),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(child: Text(title, style: Theme.of(context).textTheme.headlineMedium)),
                  ...actions,
                ],
              ),
              const SizedBox(height: 6),
              Text(subtitle, style: Theme.of(context).textTheme.bodyLarge),
              const SizedBox(height: 24),
              ...children,
            ],
          ),
        ),
      ),
    );
    return SafeArea(
      child: onRefresh == null ? content : RefreshIndicator(onRefresh: onRefresh!, child: content),
    );
  }
}

/// Loads data, shows a spinner or a retryable error, and reloads whenever
/// [Api.changes] fires (e.g. after a test is submitted on another tab).
class Loader<T> extends StatefulWidget {
  const Loader({super.key, required this.load, required this.builder});

  final Future<T> Function() load;
  final Widget Function(BuildContext context, T data, Future<void> Function() reload) builder;

  @override
  State<Loader<T>> createState() => _LoaderState<T>();
}

class _LoaderState<T> extends State<Loader<T>> {
  T? _data;
  Object? _error;

  @override
  void initState() {
    super.initState();
    Api.instance.changes.addListener(_reload);
    _reload();
  }

  @override
  void dispose() {
    Api.instance.changes.removeListener(_reload);
    super.dispose();
  }

  Future<void> _reload() async {
    try {
      final data = await widget.load();
      if (mounted) {
        setState(() {
          _data = data;
          _error = null;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = e);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_data != null) return widget.builder(context, _data as T, _reload);
    if (_error != null) {
      return Center(child: Padding(padding: const EdgeInsets.all(24), child: ErrorCard(_error!, onRetry: _reload)));
    }
    return const Center(child: CircularProgressIndicator());
  }
}

class ErrorCard extends StatelessWidget {
  const ErrorCard(this.error, {super.key, this.onRetry});

  final Object error;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      color: scheme.errorContainer,
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(children: [
              Icon(Icons.cloud_off, color: scheme.onErrorContainer),
              const SizedBox(width: 10),
              Expanded(child: Text('$error', style: TextStyle(color: scheme.onErrorContainer))),
            ]),
            if (onRetry != null) ...[
              const SizedBox(height: 12),
              FilledButton.tonal(onPressed: onRetry, child: const Text('Try again')),
            ],
          ],
        ),
      ),
    );
  }
}

void showError(BuildContext context, Object error) {
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$error')));
}

/// Responsive grid of equal-width cards (1-3 columns).
class CardGrid extends StatelessWidget {
  const CardGrid({super.key, required this.children});
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, constraints) {
      final width = constraints.maxWidth;
      final columns = width >= 850 ? 3 : width >= 560 ? 2 : 1;
      final cardWidth = (width - ((columns - 1) * 12)) / columns;
      return Wrap(
        spacing: 12,
        runSpacing: 12,
        children: children.map((e) => SizedBox(width: cardWidth, child: e)).toList(),
      );
    });
  }
}

class InfoCard extends StatelessWidget {
  const InfoCard({
    super.key,
    required this.title,
    required this.value,
    required this.icon,
    this.caption,
  });

  final String title;
  final String value;
  final IconData icon;
  final String? caption;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Row(
          children: [
            CircleAvatar(child: Icon(icon)),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: Theme.of(context).textTheme.labelLarge),
                  const SizedBox(height: 4),
                  Text(value, style: Theme.of(context).textTheme.titleLarge),
                  if (caption != null) ...[
                    const SizedBox(height: 4),
                    Text(caption!),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class SectionTitle extends StatelessWidget {
  const SectionTitle(this.text, {super.key});
  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 12, bottom: 10),
      child: Text(text, style: Theme.of(context).textTheme.titleLarge),
    );
  }
}
