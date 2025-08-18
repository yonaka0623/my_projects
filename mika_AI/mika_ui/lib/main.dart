import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

void main() {
  runApp(const MikaApp());
}

class MikaApp extends StatefulWidget {
  const MikaApp({super.key});
  @override
  State<MikaApp> createState() => _MikaAppState();
}

class _MikaAppState extends State<MikaApp> {
  /// Python側の emotion（HAPPY/SHY/...）→ 画像ファイル名 の対応表
  static const Map<String, String> emotionImageMap = {
    "NEUTRAL": "neutral.png",
    "HAPPY": "smile.png",
    "SAD": "sad.png",
    "SHY": "blush.png",
    "ANGRY": "angry.png",
  };

  String _currentEmotion = "NEUTRAL"; // 受け取った感情タグ（大文字で保持）
  String _lastText = "";              // 受け取った本文（必要なら表示）
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    // 2秒ごとに Python の /last をポーリング
    _timer = Timer.periodic(const Duration(seconds: 2), (_) => _fetchLatest());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _fetchLatest() async {
    try {
      final res = await http
          .get(Uri.parse('http://127.0.0.1:8000/last'))
          .timeout(const Duration(milliseconds: 900));

      if (res.statusCode == 200) {
        final data = jsonDecode(res.body) as Map<String, dynamic>;
        final emotion =
            ((data['emotion'] ?? 'NEUTRAL') as String).toUpperCase();
        final text = (data['text'] ?? '') as String;

        if (!mounted) return;
        if (emotion != _currentEmotion || text != _lastText) {
          setState(() {
            _currentEmotion = emotion;
            _lastText = text;
          });
        }
      }
    } catch (_) {
      // Python未起動・CORS等の一時エラーは無視（必要なら debugPrint で出力）
    }
  }

  String _imagePathForEmotion(String emotionUpper) {
    final fileName =
        emotionImageMap[emotionUpper] ?? emotionImageMap["NEUTRAL"]!;
    return 'assets/images/$fileName';
  }

  @override
  Widget build(BuildContext context) {
    final imagePath = _imagePathForEmotion(_currentEmotion);

    return MaterialApp(
      debugShowCheckedModeBanner: false,
      home: Scaffold(
        backgroundColor: Colors.black,
        body: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              // 表情画像
              Image.asset(
                imagePath,
                width: 300,
                height: 300,
                fit: BoxFit.contain,
              ),
              const SizedBox(height: 16),
              // 返答テキスト（不要ならこのブロック削除OK）
              if (_lastText.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: Text(
                    _lastText,
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: Colors.white, fontSize: 16),
                  ),
                ),
              const SizedBox(height: 8),
              // 現在の感情名
              Text(
                'Emotion: $_currentEmotion',
                style: const TextStyle(color: Colors.grey),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
