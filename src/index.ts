import * as p from '@clack/prompts';
import pc from 'picocolors';
import cliProgress from 'cli-progress';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

// 深蓝色方形笑脸：用背景色块拼成，不使用任何图片或 Emoji
function renderLogo(): void {
    const B = (s: string) => pc.bgBlue(pc.white(s));
    const _ = (s: string) => pc.bgBlue(s);
    const lines = [
        B('                   '),
        B('   ·           ·   '),
        B('                   '),
        B('     ╰───────╯     '),
        B('                   '),
    ];
    for (const line of lines) {
        process.stdout.write('  ' + line + '\n');
    }
}

async function main(): Promise<void> {
    console.clear();

    // ── 初始 UI：Logo + 标题（即时渲染）──────────────────
    renderLogo();
    console.log(
        '\n  ' +
        pc.bgBlue(pc.white(' HERIS ')) +
        '  ' +
        pc.bold(pc.white('AI 智能助手')) +
        pc.dim('  v0.1.0')
    );
    console.log('  ' + pc.dim('─'.repeat(34)) + '\n');

    // ── 进度条：仅此时显示，加载完成后自动消失 ───────────
    const bar = new cliProgress.SingleBar(
        {
            format:
                '  ' +
                pc.blue('{bar}') +
                ' ' +
                pc.dim('{percentage}%') +
                pc.dim('  正在加载...'),
            barCompleteChar: '█',
            barIncompleteChar: '░',
            hideCursor: true,
            clearOnComplete: true,
        },
        cliProgress.Presets.shades_classic
    );

    bar.start(100, 0);
    for (let i = 0; i <= 100; i += 4) {
        bar.update(i);
        await new Promise<void>(r => setTimeout(r, 30));
    }
    bar.update(100);
    bar.stop();

    // ── 模式选择（进度条消失后显示）──────────────────────
    console.log(
        '  ' + pc.bgBlue(pc.white(' HERIS ')) +
        '  ' + pc.dim('选择一种模式开始对话')
    );
    console.log();

    const mode = await p.select({
        message: pc.white('请选择运行模式') + pc.dim(' (↑/↓ 切换  Enter 确认)'),
        options: [
            {
                value: 'normal',
                label: pc.bgWhite(pc.black(' 普通 ')) + '  普通模式',
                hint: '专业高效地完成任务',
            },
            {
                value: 'push',
                label: pc.bgYellow(pc.black(' PUSH ')) + '  PUSH 模式',
                hint: '元气满满，用乐观积极的态度感染你',
            },
            {
                value: 'slackin',
                label: pc.bgGreen(pc.black(' 摸鱼 ')) + '  摸鱼模式',
                hint: '轻松佛系，在放松的状态下慢慢来',
            },
        ],
        initialValue: 'normal',
    });

    if (p.isCancel(mode)) {
        p.cancel(pc.dim('已取消'));
        process.exit(0);
    }

    const modeLabels: Record<string, string> = {
        normal:  pc.bgWhite(pc.black(' 普通 ')),
        push:    pc.bgYellow(pc.black(' PUSH ')),
        slackin: pc.bgGreen(pc.black(' 摸鱼 ')),
    };

    console.log(
        '\n  ' +
        modeLabels[mode as string] +
        pc.dim('  已启动，输入任务开始对话\n')
    );

    // 将选中的模式写入临时文件，供 Python 后端读取
    const tmpFile = path.join(os.tmpdir(), 'heris_mode_selection');
    fs.writeFileSync(tmpFile, mode as string, 'utf-8');
}

main().catch(err => {
    console.error(err);
    process.exit(1);
});
