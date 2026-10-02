package io.github.mcdrsingleplayer.mixin;

import io.github.mcdrsingleplayer.RestoreProgressMonitor;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.screens.TitleScreen;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** Loading screens do not show the title logo and splash behind their text. */
@Mixin(TitleScreen.class)
abstract class RestoreTitleScreenMixin {
    @Inject(method = "extractRenderState", at = @At("HEAD"), cancellable = true)
    private void hideTitleDecorationDuringRestore(GuiGraphicsExtractor graphics, int mouseX,
            int mouseY, float ticks, CallbackInfo callback) {
        if (RestoreProgressMonitor.hasVisibleProgress()) callback.cancel();
    }
}
