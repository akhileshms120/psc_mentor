import 'package:flutter/material.dart';

import 'app.dart';
import 'core/api.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Api.instance.load();
  runApp(const PscMentorApp());
}
